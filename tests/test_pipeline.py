import json, os, sys, tempfile, unittest, sqlite3
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from canon.seed import build
from engine import engine as E
from orchestrator import pipeline as P, llm

def setup():
    d = tempfile.mkdtemp(); base = os.path.join(d, "m.db"); build(base).close()
    return d, base, os.path.join(d, "m.draft.db")

class T(unittest.TestCase):
    def test_bozza_non_tocca_il_canone(self):
        d, base, dr = setup(); m = llm.MockProvider()
        r = P.draft(m, base, dr)
        self.assertEqual(r["status"], "bozza")
        self.assertEqual(E.current_cycle(sqlite3.connect(base)), 5)      # canone intatto
        self.assertEqual(E.current_cycle(sqlite3.connect(dr)), 6)        # bozza avanzata
        self.assertTrue(r["ok_editor"])

    def test_approve_promuove_e_reject_scarta(self):
        d, base, dr = setup(); P.draft(llm.MockProvider(), base, dr)
        path = P.approve(base, dr, os.path.join(d, "content"))
        self.assertTrue(os.path.exists(path)); self.assertFalse(os.path.exists(dr))
        c = sqlite3.connect(base); self.assertEqual(E.current_cycle(c), 6)
        self.assertEqual(c.execute("SELECT status FROM chapters WHERE cycle=6").fetchone()[0], "approvato")
        P.draft(llm.MockProvider(), base, dr); P.reject(dr); self.assertFalse(os.path.exists(dr))

    def test_character_agent_non_vede_segreti_altrui(self):
        d, base, dr = setup(); m = llm.MockProvider(); P.draft(m, base, dr)
        for role, system, user in m.calls:
            if role == "character" and "[elia]" in user.split("\n")[0]:
                self.assertNotIn("opzioni Aurelia", user)          # f08: solo Arthur e Nadia
                self.assertNotIn("fondo occulto", user)            # f04: solo Arthur e Sofia
            if role == "character" and "[sofia]" in user.split("\n")[0]:
                self.assertNotIn("2.400 pazienti", user)           # f01: segreto di Elia
        self.assertTrue(any(r == "character" for r, _, _ in m.calls))

    def test_world_keeper_rifiuta_ops_non_ammesse(self):
        d, base, dr = setup()
        wk = json.dumps({"approved": True, "ops": [
            {"op": "delete_everything"},
            {"op": "add_knowledge", "entity": "marco", "fact_id": "f01", "certainty": "sa"},   # morto
            {"op": "add_knowledge", "entity": "elia", "fact_id": "f99", "certainty": "sa"},    # fatto inesistente
            {"op": "add_fact", "subject": "arthur", "predicate": "ha_pagato", "object": "Nadia", "secret": True},
            {"op": "add_knowledge", "entity": "nadia", "fact_id": "new:1", "certainty": "sa"}]})
        r = P.draft(llm.MockProvider({"world_keeper": [wk]}), base, dr)
        self.assertEqual(len(r["ops_rifiutate"]), 3); self.assertEqual(r["ops_applicate"], 2)
        c = sqlite3.connect(dr)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM facts").fetchone()[0], 11)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM knowledge WHERE entity_id='nadia' AND fact_id='f11'").fetchone()[0], 1)

    def test_world_keeper_puo_rifiutare_il_ciclo(self):
        d, base, dr = setup()
        r = P.draft(llm.MockProvider({"world_keeper": [json.dumps({"approved": False, "objections": ["incoerente"]})]}), base, dr)
        self.assertEqual(r["status"], "rifiutato"); self.assertFalse(os.path.exists(dr))

    def test_veto_alla_morte(self):
        d, base, dr = setup(); c = sqlite3.connect(base)
        seed = next(s for s in range(500) if any(e["victim"] for e in E.propose_cycle(c, f"v{s}")["events"]))
        p = E.propose_cycle(c, f"v{seed}"); idx = next(e["idx"] for e in p["events"] if e["victim"]); victim = next(e["victim"] for e in p["events"] if e["victim"])
        wk = json.dumps({"approved": True, "vetoes": [{"event_idx": idx, "reason": "prematura"}], "ops": []})
        P.draft(llm.MockProvider({"world_keeper": [wk]}), base, dr, f"v{seed}")
        self.assertEqual(sqlite3.connect(dr).execute("SELECT status FROM entities WHERE id=?", (victim,)).fetchone()[0], "vivo")

    def test_ciclo_editor_revisione_e_lint(self):
        d, base, dr = setup()
        bad = "# Capitolo 6\n\nIl Corriere della Sera scrisse tutto. Risk: 9.\n"
        good = "# Capitolo 6\n\nIl quotidiano milanese scrisse tutto.\n"
        m = llm.MockProvider({"novelist": [bad, good]})
        r = P.draft(m, base, dr)
        self.assertEqual(r["revisioni"], 1); self.assertTrue(r["ok_editor"])
        # se il romanziere non si corregge mai: bozza segnalata, non scartata
        d, base, dr = setup()
        r = P.draft(llm.MockProvider({"novelist": [bad, bad, bad]}), base, dr)
        self.assertFalse(r["ok_editor"]); self.assertEqual(r["revisioni"], 2)
        self.assertIn("REVIEW", sqlite3.connect(dr).execute("SELECT body_md FROM chapters").fetchone()[0])

    def test_json_malformato_blocca_senza_toccare_il_canone(self):
        d, base, dr = setup()
        with self.assertRaises(Exception): P.draft(llm.MockProvider({"character": ["non e json"]}), base, dr)
        self.assertEqual(E.current_cycle(sqlite3.connect(base)), 5)

if __name__ == "__main__": unittest.main(verbosity=2)
