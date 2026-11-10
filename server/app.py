"""Server locale della Control Room (solo 127.0.0.1). Legge dal canone e permette approva/scarta/verifica.
Difese: ascolto solo in locale, controllo dell'header Host (anti DNS-rebinding), header custom obbligatorio
sui POST (anti CSRF da altre pagine web), limite alla dimensione delle richieste."""
import json, os, re, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from canon import db as DB
from orchestrator import pipeline as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_OK = {"verificato", "corretto", "fittizio"}

def build_state(base_db, draft_db):
    c = DB.connect(base_db)
    q = lambda sql, *a: c.execute(sql, a).fetchall()
    cycle = c.execute("SELECT COALESCE(MAX(cycle),0) FROM cycles").fetchone()[0]
    ents = []
    for i, k, n, r, t, pl, st, dc in q("SELECT id,kind,name,role,tier,place,status,died_cycle FROM entities ORDER BY tier, name"):
        ents.append(dict(id=i, kind=k, name=n, role=r, tier=t, place=pl, status=st, died=dc,
                         stats=dict(q("SELECT stat,value FROM stats WHERE entity_id=?", i))))
    state = dict(cycle=cycle, entities=ents,
        relations=[dict(a=a, b=b, type=t, label=l, strength=s, closed=v) for a, b, t, l, s, v in q("SELECT a,b,type,label,strength,valid_to FROM relations")],
        events=[dict(id=i, cycle=cy, kind=k, name=n, actor=a, cause=ca, location=lo, description=d, origin=o)
                for i, cy, k, n, a, ca, lo, d, o in q("SELECT id,cycle,kind,name,actor,cause_event_id,location,description,origin FROM events ORDER BY cycle,id")],
        facts=[dict(id=i, subject=s, predicate=p, object=o, secret=bool(sec)) for i, s, p, o, sec in q("SELECT f.id,f.subject,f.predicate,f.object,(SELECT 1 FROM secrets WHERE fact_id=f.id) FROM facts f")],
        knowledge=[dict(entity=e, fact=f, certainty=ce, cycle=cy) for e, f, ce, cy in q("SELECT entity_id,fact_id,certainty,learned_cycle FROM knowledge")],
        promises=[dict(id=i, description=d, opened=o, closed=cl, age=(None if cl is not None else cycle - o), overdue=(cl is None and cycle - o >= 4))
                  for i, d, o, cl in q("SELECT id,description,opened_cycle,closed_cycle FROM promises ORDER BY opened_cycle")],
        notes=[dict(id=i, cycle=cy, kind=k, description=d, due=du, resolved=r) for i, cy, k, d, du, r in q("SELECT id,cycle,kind,description,due_cycle,resolved_cycle FROM plot_notes ORDER BY id")],
        claims=[dict(id=i, cycle=cy, domain=d, context=cx, verdict=v, note=n, correction=co, hint=h, status=st, url=u)
                for i, cy, d, cx, v, n, co, h, st, u in q("SELECT id,cycle,domain,context,verdict,advisor_note,correction,search_hint,status,source_url FROM tech_claims ORDER BY cycle DESC,id")],
        chapters=[dict(cycle=cy, body=b) for cy, b in q("SELECT cycle,body_md FROM chapters WHERE status='approvato' ORDER BY cycle")],
        draft=None)
    c.close()
    if os.path.exists(draft_db):
        d = DB.connect(draft_db)
        row = d.execute("SELECT cycle,body_md FROM chapters WHERE status='bozza' ORDER BY cycle DESC LIMIT 1").fetchone()
        if row:
            cy, body = row
            state["draft"] = dict(cycle=cy, body=body,
                events=[dict(id=i, cycle=cy, kind=k, name=n, actor=a, cause=ca, location=lo, description=de, origin="engine")
                        for i, k, n, a, ca, lo, de in d.execute("SELECT id,kind,name,actor,cause_event_id,location,description FROM events WHERE cycle=? ORDER BY id", (cy,))],
                claims=[dict(id=i, domain=dm, context=cx, verdict=v, note=n, correction=co, hint=h, status=st, url=u)
                        for i, dm, cx, v, n, co, h, st, u in d.execute("SELECT id,domain,context,verdict,advisor_note,correction,search_hint,status,source_url FROM tech_claims WHERE cycle=? ORDER BY id", (cy,))])
        d.close()
    return state

def make_handler(base_db, draft_db, out_dir, port_getter):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _send(self, code, obj=None, raw=None, ctype="application/json; charset=utf-8"):
            body = raw if raw is not None else json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
        def _host_ok(self):
            p = port_getter(); return self.headers.get("Host", "") in (f"127.0.0.1:{p}", f"localhost:{p}")
        def do_GET(self):
            if not self._host_ok(): return self._send(403, {"errore": "host non ammesso"})
            if self.path in ("/", "/index.html"):
                with open(os.path.join(ROOT, "control_room", "index.html"), "rb") as f:
                    raw = f.read()
                return self._send(200, raw=raw, ctype="text/html; charset=utf-8")
            if self.path == "/api/state": return self._send(200, build_state(base_db, draft_db))
            self._send(404, {"errore": "non trovato"})
        def do_POST(self):
            if not self._host_ok(): return self._send(403, {"errore": "host non ammesso"})
            if self.headers.get("X-Mnemosine") != "1": return self._send(403, {"errore": "header mancante"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 65536: return self._send(413, {"errore": "richiesta troppo grande"})
            try: data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError: return self._send(400, {"errore": "JSON non valido"})
            try:
                if self.path == "/api/approve":
                    unv = P.unverified_count(draft_db) if os.path.exists(draft_db) else 0
                    path = P.approve(base_db, draft_db, out_dir); return self._send(200, {"ok": True, "file": path, "non_verificate": unv})
                if self.path == "/api/reject": P.reject(draft_db); return self._send(200, {"ok": True})
                if self.path == "/api/verify":
                    cid, st, url = data.get("id"), data.get("status"), (data.get("url") or "").strip()
                    if not isinstance(cid, int) or st not in STATUS_OK: return self._send(400, {"errore": "id o stato non validi"})
                    if st == "verificato" and not re.match(r"^https?://\S+$", url): return self._send(400, {"errore": "per 'verificato' serve un URL http(s) della fonte"})
                    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
                    for path in (base_db, draft_db):
                        if os.path.exists(path):
                            cc = DB.connect(path); cc.execute("UPDATE tech_claims SET status=?, source_url=?, verified_at=? WHERE id=?", (st, url or None, now, cid)); cc.commit(); cc.close()
                    return self._send(200, {"ok": True})
            except RuntimeError as e: return self._send(400, {"errore": str(e)})
            except Exception: return self._send(500, {"errore": "errore interno: controlla il terminale"})
            self._send(404, {"errore": "non trovato"})
    return H

def serve(base_db="mnemosine.db", draft_db="mnemosine.draft.db", out_dir="content", port=8765):
    if not os.path.exists(base_db): raise SystemExit(f"Canone non trovato ({base_db}). Esegui prima: python run.py init")
    holder = {}
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(base_db, draft_db, out_dir, lambda: holder["port"]))
    holder["port"] = srv.server_address[1]
    return srv
