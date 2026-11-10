import http.client, json, os, sys, tempfile, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from canon.seed import build
from canon import db as DB
from orchestrator import pipeline as P, llm, plot as PL, advisors as AD
from server.app import serve

def setup():
    d = tempfile.mkdtemp(); base = os.path.join(d, "m.db"); build(base).close()
    return d, base, os.path.join(d, "m.draft.db")

MARK_TXT = "# Capitolo 6\n\nIl biomarker raggiunge una sensibilita del 91%. [[VERIFICA: sensibilita p-tau217]]\n\nLa societa cede il 25% delle royalty. [[VERIFICA: struttura royalty]]\n"

class Plot(unittest.TestCase):
    def test_debiti_in_ritardo(self):
        d, base, _ = setup(); c = DB.connect(base)
        r = PL.debt_report(c, 6); late = {p["id"] for p in r["promises"] if p["overdue"]}
        self.assertEqual(late, {"p07"})                        # aperta al ciclo 2: eta 4
        self.assertTrue(r["twist_allowed"])

    def test_validazione_piano(self):
        d, base, dr = setup(); m = llm.MockProvider(); P.draft(m, base, dr); c = DB.connect(dr)   # bozza ciclo 6
        plan = {"scene_plan": [
            {"pov": "arthur", "evento_id": "c06-00", "scopo": "ok", "avanza": ["p07", "p99"]},
            {"pov": "marco", "evento_id": "c06-00", "scopo": "morto non agisce"},
            {"pov": "elia", "evento_id": "e01", "scopo": "evento di un altro ciclo"}],
            "plant": [{"descrizione": "seme valido", "due_cycle": 9}, {"descrizione": "troppo lontano", "due_cycle": 99}, {"descrizione": "passato", "due_cycle": 3}],
            "payoff": [999], "twist": {"descrizione": "colpo di scena"}}
        clean, scarti, avvisi = PL.validate_plan(c, 6, plan, {"elia", "arthur", "sofia"})
        self.assertEqual(len(clean["scene_plan"]), 1); self.assertEqual(clean["scene_plan"][0]["avanza"], ["p07"])
        self.assertEqual(len(clean["plant"]), 1); self.assertEqual(clean["payoff"], []); self.assertEqual(clean["twist"], {"descrizione": "colpo di scena"})
        self.assertEqual(avvisi, [])                           # il debito in ritardo e stato avanzato
        PL.apply_plan(c, 6, clean)
        c.execute("INSERT INTO plot_notes(cycle,kind,description,resolved_cycle) VALUES(6,'twist','x',6)")
        _, scarti2, _ = PL.validate_plan(c, 7, {"scene_plan": [], "twist": {"descrizione": "ancora"}}, {"elia"})
        self.assertTrue(any("twist" in s for s in scarti2))    # cooldown di 3 cicli

    def test_debito_ignorato_segnalato(self):
        d, base, dr = setup(); P.draft(llm.MockProvider(), base, dr); c = DB.connect(dr)
        _, _, avvisi = PL.validate_plan(c, 6, {"scene_plan": [{"pov": "arthur", "evento_id": "c06-00", "scopo": "x"}]}, {"arthur"})
        self.assertEqual(avvisi, [{"debiti_ignorati": ["p07"]}])

class Advisors(unittest.TestCase):
    def test_estrazione_e_dominio(self):
        cl = AD.extract_claims(MARK_TXT)
        self.assertEqual(len(cl), 2); self.assertEqual(cl[0]["domain"], "biotech"); self.assertEqual(cl[1]["domain"], "finanza")
        self.assertIn("sensibilita del 91%", cl[0]["context"])

    def test_pipeline_piano_advisor_e_export(self):
        d, base, dr = setup()
        plan = json.dumps({"scene_plan": [{"pov": "arthur", "evento_id": "c06-00", "scopo": "scopo-test", "avanza": ["p07"]}], "plant": [{"descrizione": "seme", "due_cycle": 8}], "payoff": [], "twist": None})
        bio = json.dumps({"verdetti": [{"id": 1, "verdetto": "ok", "nota": "plausibile", "da_cercare": "validazione p-tau217"}]})
        fin = json.dumps({"verdetti": [{"id": 1, "verdetto": "incerto", "nota": "dipende dal contratto"}]})
        m = llm.MockProvider({"plot_architect": [plan], "advisor_biotech": [bio], "advisor_finance": [fin], "novelist": [MARK_TXT]})
        r = P.draft(m, base, dr)
        self.assertEqual(r["piano_scene"], 1); self.assertEqual(r["avvisi_trama"], []); self.assertEqual(r["affermazioni_tecniche"], 2)
        nov = [u for ro, s, u in m.calls if ro == "novelist"][0]
        self.assertIn("PIANO DEL CAPITOLO", nov); self.assertIn("scopo-test", nov)
        c = DB.connect(dr)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM tech_claims WHERE status='non_verificato'").fetchone()[0], 2)   # giudizio != verifica
        self.assertEqual(c.execute("SELECT COUNT(*) FROM plot_notes WHERE kind='foreshadow'").fetchone()[0], 1)
        self.assertEqual(P.unverified_count(dr), 2)
        path = P.approve(base, dr, os.path.join(d, "out"))
        txt = open(path, encoding="utf-8").read()
        self.assertNotIn("[[VERIFICA", txt); self.assertIn("sensibilita del 91%", txt)
        ver = open(path.replace(".md", ".verifiche.md"), encoding="utf-8").read()
        self.assertIn("non_verificato", ver); self.assertIn("non una verifica", ver)

    def test_correzione_advisor_forza_revisione(self):
        d, base, dr = setup()
        bio = json.dumps({"verdetti": [{"id": 1, "verdetto": "correggere", "nota": "numero troppo preciso", "correzione": "oltre il 90%"}]})
        m = llm.MockProvider({"advisor_biotech": [bio], "novelist": [MARK_TXT, "# Capitolo 6\n\nIl test e molto sensibile.\n"]})
        r = P.draft(m, base, dr)
        self.assertEqual(r["revisioni"], 1)
        rev = [u for ro, s, u in m.calls if ro == "novelist"][1]
        self.assertIn("oltre il 90%", rev)

class Server(unittest.TestCase):
    def setUp(self):
        self.d, self.base, self.dr = setup()
        P.draft(llm.MockProvider({"novelist": [MARK_TXT]}), self.base, self.dr)
        self.srv = serve(self.base, self.dr, os.path.join(self.d, "out"), 0)
        self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close()
    def req(self, method, path, body=None, headers=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port); h = {"Host": host or f"127.0.0.1:{self.port}"}; h.update(headers or {})
        c.request(method, path, json.dumps(body) if body is not None else None, h); r = c.getresponse(); return r.status, r.read()

    def test_stato_e_bozza(self):
        s, b = self.req("GET", "/api/state"); st = json.loads(b)
        self.assertEqual(s, 200); self.assertEqual(st["cycle"], 5); self.assertEqual(st["draft"]["cycle"], 6)
        self.assertEqual(len(st["events"]), 24); self.assertEqual(len(st["draft"]["claims"]), 2)
        s, b = self.req("GET", "/"); self.assertEqual(s, 200); self.assertIn(b"Mnemosine", b)

    def test_sicurezza(self):
        self.assertEqual(self.req("GET", "/api/state", host="evil.example")[0], 403)                 # DNS rebinding
        self.assertEqual(self.req("POST", "/api/reject", {})[0], 403)                                 # senza header (CSRF)
        self.assertEqual(self.req("POST", "/api/reject", {}, {"X-Mnemosine": "1"}, host="evil.example")[0], 403)
        self.assertTrue(os.path.exists(self.dr))                                                      # nulla e stato scartato

    def test_verifica_richiede_fonte_e_aggiorna_entrambi_i_db(self):
        h = {"X-Mnemosine": "1"}
        cid = json.loads(self.req("GET", "/api/state")[1])["draft"]["claims"][0]["id"]
        self.assertEqual(self.req("POST", "/api/verify", {"id": cid, "status": "verificato", "url": "javascript:alert(1)"}, h)[0], 400)
        self.assertEqual(self.req("POST", "/api/verify", {"id": cid, "status": "boh"}, h)[0], 400)
        self.assertEqual(self.req("POST", "/api/verify", {"id": cid, "status": "verificato", "url": "https://example.org/doc"}, h)[0], 200)
        self.assertEqual(DB.connect(self.dr).execute("SELECT status FROM tech_claims WHERE id=?", (cid,)).fetchone()[0], "verificato")

    def test_approva_dal_server(self):
        h = {"X-Mnemosine": "1"}
        s, b = self.req("POST", "/api/approve", {}, h); j = json.loads(b)
        self.assertEqual(s, 200); self.assertEqual(j["non_verificate"], 2); self.assertTrue(os.path.exists(j["file"]))
        self.assertIsNone(json.loads(self.req("GET", "/api/state")[1])["draft"])
        self.assertEqual(self.req("POST", "/api/approve", {}, h)[0], 400)                              # nessuna bozza

if __name__ == "__main__": unittest.main(verbosity=2)
