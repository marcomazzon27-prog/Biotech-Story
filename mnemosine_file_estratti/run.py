"""Uso:
  python run.py init                 crea mnemosine.db dal canone storico (Cicli 1-5)
  python run.py propose [seed]       mostra il prossimo ciclo SENZA scriverlo
  python run.py commit  [seed]       valida e scrive il ciclo nel canone
  python run.py state                stato attuale, morti e promesse aperte
  python run.py draft [provider] [seed]   Fase 2: ciclo assistito su una BOZZA (provider: mock|manual|anthropic)
  python run.py approve              porta la bozza nel canone ed esporta il capitolo in content/
  python run.py reject               scarta la bozza
  python run.py read                 legge la bozza in corso
  python run.py serve [porta]        Control Room collegata al canone (http://127.0.0.1:8765)
  python run.py claims               elenca le affermazioni tecniche e il loro stato
  python run.py verify <id> <url>    segna come verificata un'affermazione (serve la fonte)"""
import sys, sqlite3, os, json
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from canon.seed import build
from engine import engine as E
DB = "mnemosine.db"
DRAFT = "mnemosine.draft.db"

def show(p):
    print(f"Ciclo {p['cycle']}  (seed {p['seed']})")
    for ev in p["events"]:
        pre = "  ↳ catena di #%d" % ev["cause"] if ev["cause"] is not None else ""
        extra = f" | {ev['personal']} | {ev['consequence']} | reazione {ev['reaction']}" if ev["personal"] else ""
        vic = f"  💀 vittima: {ev['victim']}" if ev["victim"] else ""
        print(f" #{ev['idx']} [{ev['actor']}] {ev['name']}{extra}{pre}{vic}\n      effetti {ev['effects']}")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "state"
    seed = sys.argv[2] if len(sys.argv) > 2 else "mnemosine"
    if cmd in ("draft", "approve", "reject"):
        from orchestrator import pipeline as P, llm
        if cmd == "draft":
            prov = llm.make(sys.argv[2] if len(sys.argv) > 2 else "mock"); sd = sys.argv[3] if len(sys.argv) > 3 else "mnemosine"
            r = P.draft(prov, DB, DRAFT, sd); print(json.dumps(r, ensure_ascii=False, indent=1))
            if r["status"] == "bozza": print("\nBozza pronta. Leggi il capitolo con:  python run.py read   | poi: approve / reject")
        elif cmd == "approve":
            n = P.unverified_count(DRAFT); print("Approvato ->", P.approve(DB, DRAFT, "content"))
            if n: print(f"Attenzione: {n} affermazioni tecniche NON ancora verificate (vedi file .verifiche.md e `python run.py claims`).")
        else: P.reject(DRAFT); print("Bozza scartata.")
        sys.exit()
    if cmd == "serve":
        from server.app import serve
        srv = serve(DB, DRAFT, "content", int(sys.argv[2]) if len(sys.argv) > 2 else 8765)
        print(f"Control Room: http://127.0.0.1:{srv.server_address[1]}  (Ctrl+C per fermare)")
        try: srv.serve_forever()
        except KeyboardInterrupt: print("\nFermato.")
        sys.exit()
    if cmd in ("claims", "verify"):
        from canon import db as DBm
        cc = DBm.connect(DB)
        if cmd == "verify":
            cc.execute("UPDATE tech_claims SET status='verificato', source_url=? WHERE id=?", (sys.argv[3], int(sys.argv[2]))); cc.commit(); print("Segnata come verificata.")
        else:
            for i, cy, d, cx, v, st in cc.execute("SELECT id,cycle,domain,context,verdict,status FROM tech_claims ORDER BY cycle DESC,id"): print(f"#{i} c{cy} [{st}] ({d}, advisor: {v}) {cx[:90]}")
        sys.exit()
    if cmd == "read":
        if not os.path.exists(DRAFT): sys.exit("Nessuna bozza in corso.")
        c = sqlite3.connect(DRAFT); print(c.execute("SELECT body_md FROM chapters WHERE status='bozza' ORDER BY cycle DESC LIMIT 1").fetchone()[0]); sys.exit()
    if cmd == "init": build(DB).close(); print("Creato", DB); sys.exit()
    c = sqlite3.connect(DB)
    if cmd == "propose": show(E.propose_cycle(c, seed))
    elif cmd == "commit":
        p = E.propose_cycle(c, seed); show(p); E.commit(c, p); print("-> scritto nel canone")
    else:
        print("Ciclo corrente:", E.current_cycle(c))
        for r in c.execute("SELECT e.name,s.stat,s.value FROM stats s JOIN entities e ON e.id=s.entity_id ORDER BY e.name"): print(" ", r)
        print("Morti:", [r[0] for r in c.execute("SELECT name FROM entities WHERE status='morto'")])
        print("Promesse aperte:"); [print("  -", r[0]) for r in c.execute("SELECT description FROM promises WHERE closed_cycle IS NULL")]
