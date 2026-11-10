"""Pipeline assistita Fase 2: propose -> Character Agents -> World Keeper -> commit -> Novelist <-> Continuity Editor.
Tutto avviene su una COPIA del database (bozza). Nulla entra nel canone senza approve()."""
import json, os, re, shutil, sqlite3
from canon import db as DB
from engine import engine as E
from orchestrator import context as C, plot as PL, advisors as AD
from orchestrator.util import parse_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def _prompt(name): return open(os.path.join(ROOT, "agents", "prompts", name + ".md"), encoding="utf-8").read()
CERT = {"sa", "sospetta", "crede_falso"}
SHEETS = {
 "elia": "Idealista pragmatico. Ferita: madre morta di Alzheimer. Obiettivo: validare il biomarker. Tic: si tocca la cicatrice sul sopracciglio destro quando mente. Non mente mai direttamente: omette.",
 "arthur": "Spietato paziente, parla in terza persona quando mente. Ferita: deterioramento cognitivo. Tremore alla mano destra nascosto con un bicchiere. Non alza mai la voce.",
 "sofia": "Ambiziosa ma leale. Voce bassa e calda, metallica quando negozia. Ferita: padre malato. Segreto: deve favorire un fondo collegato ad Arthur.",
}

def lint(text):
    """Controlli deterministici prima dell'editor LLM: nomi reali e fughe di meccaniche di gioco."""
    issues = []
    for line in open(os.path.join(ROOT, "compliance", "blocklist.txt"), encoding="utf-8"):
        w = line.strip()
        if w and not w.startswith("#") and w.lower() in text.lower():
            issues.append({"tipo": "reale", "citazione": w, "correzione": "sostituire con un nome fittizio"})
    for m in re.finditer(r"\b(power|money|guilt|risk|rep|bonds|health)\s*[:=]\s*\d+|\b(d6|d12|2d6|dado|motore)\b", text, re.I):
        issues.append({"tipo": "altro", "citazione": m.group(0), "correzione": "rimuovere riferimenti alle meccaniche"})
    return issues

def apply_ops(conn, cycle, ops):
    """Applica solo le operazioni ammesse; restituisce (applicate, rifiutate)."""
    ok, bad, newids = [], [], {}
    alive = {r[0] for r in conn.execute("SELECT id FROM entities WHERE kind='persona' AND status='vivo'")}
    ents = {r[0] for r in conn.execute("SELECT id FROM entities")}
    n_new = 0
    for op in ops or []:
        try:
            kind = op["op"]
            if kind == "add_fact":
                if op["subject"] not in ents: raise ValueError("soggetto sconosciuto")
                fid = "f%02d" % (conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] + 1)
                conn.execute("INSERT INTO facts VALUES(?,?,?,?,1,?)", (fid, op["subject"], op["predicate"], op["object"], cycle))
                if op.get("secret"): conn.execute("INSERT INTO secrets VALUES(?,?,?)", (fid, None, "da definire"))
                n_new += 1; newids[f"new:{n_new}"] = fid
            elif kind == "add_knowledge":
                fid = newids.get(op["fact_id"], op["fact_id"])
                if op["entity"] not in alive: raise ValueError("entita non viva/non persona")
                if op["certainty"] not in CERT: raise ValueError("certezza non valida")
                if not conn.execute("SELECT 1 FROM facts WHERE id=?", (fid,)).fetchone(): raise ValueError("fatto inesistente")
                conn.execute("INSERT OR REPLACE INTO knowledge VALUES(?,?,?,?,?)", (op["entity"], fid, op["certainty"], cycle, op.get("from")))
            elif kind == "open_promise":
                pid = "p%02d-c%d" % (conn.execute("SELECT COUNT(*) FROM promises").fetchone()[0] + 1, cycle)
                conn.execute("INSERT INTO promises(id,description,opened_cycle) VALUES(?,?,?)", (pid, op["description"], cycle))
            elif kind == "close_promise":
                if not conn.execute("SELECT 1 FROM promises WHERE id=? AND closed_cycle IS NULL", (op["id"],)).fetchone(): raise ValueError("promessa non aperta")
                conn.execute("UPDATE promises SET closed_cycle=? WHERE id=?", (cycle, op["id"]))
            else: raise ValueError("operazione non ammessa")
            ok.append(op)
        except (KeyError, ValueError) as e:
            bad.append({"op": op, "motivo": str(e)})
    conn.commit()
    return ok, bad

def draft(provider, base_db, draft_db, seed="mnemosine", max_revisions=2):
    shutil.copy(base_db, draft_db)
    conn = DB.connect(draft_db)
    proposal = E.propose_cycle(conn, seed)
    cycle = proposal["cycle"]
    # 1. Character Agents (conoscenza limitata)
    by_actor = {}
    for ev in proposal["events"]: by_actor.setdefault(ev["actor"], []).append(ev)
    intents = {}
    for actor, evs in by_actor.items():
        raw = provider.complete("character", _prompt("character"), C.character_context(conn, actor, evs, SHEETS.get(actor, "")))
        d = parse_json(raw)
        for k in ("azione", "intento"):
            if k not in d: raise ValueError(f"character {actor}: manca '{k}'")
        intents[actor] = d
    # 2. World Keeper
    wk_in = (C.canon_summary(conn) + "\n\nEVENTI PROPOSTI DAL MOTORE:\n" + "\n".join(
        f"#{e['idx']} [{e['actor']}] {e['name']}" + (f" | {e['personal']} | {e['consequence']}" if e['personal'] else "") +
        (f" | VITTIMA: {e['victim']}" if e['victim'] else "") + (f" | causa: #{e['cause']}" if e['cause'] is not None else "") for e in proposal["events"]) +
        "\n\nINTENZIONI DEI PERSONAGGI:\n" + json.dumps(intents, ensure_ascii=False, indent=1))
    wk = parse_json(provider.complete("world_keeper", _prompt("world_keeper"), wk_in))
    if not wk.get("approved", False):
        conn.close(); os.remove(draft_db)
        return {"status": "rifiutato", "cycle": cycle, "motivo": wk.get("objections", [])}
    for v in wk.get("vetoes", []):
        for ev in proposal["events"]:
            if ev["idx"] == v.get("event_idx") and ev["victim"]:
                ev["victim"] = None; ev["name"] += " (tentativo fallito)"
    ids = E.commit(conn, proposal)
    ops_ok, ops_bad = apply_ops(conn, cycle, wk.get("ops"))
    # 3. Plot Architect: piano vincolante + debiti narrativi
    povs = sorted(by_actor)
    cyc_events = C.cycle_events(conn, cycle)
    pa_in = (f"CICLO {cycle}\n\nEVENTI DEL CICLO:\n{cyc_events}\n\nAZIONI DEI PERSONAGGI:\n" + json.dumps(intents, ensure_ascii=False, indent=1) +
             "\n\n" + PL.format_report(PL.debt_report(conn, cycle)))
    plan, plot_scarti, plot_avvisi = PL.validate_plan(conn, cycle, parse_json(provider.complete("plot_architect", _prompt("plot_architect"), pa_in)), set(povs))
    PL.apply_plan(conn, cycle, plan)
    # 4. Novelist <-> Continuity Editor + Advisor tecnici
    prev = conn.execute("SELECT body_md FROM chapters WHERE status='approvato' ORDER BY cycle DESC LIMIT 1").fetchone()
    nov_in = (f"CAPITOLO N. {cycle}\n\nPIANO DEL CAPITOLO (vincolante):\n{PL.format_plan(plan)}\n\nEVENTI DEL CICLO:\n{cyc_events}\n\nAZIONI DEI PERSONAGGI:\n" +
              json.dumps(intents, ensure_ascii=False, indent=1) + f"\n\nCONOSCENZE PER POV:\n{C.pov_knowledge(conn, povs)}\n\n" +
              f"PROMESSE APERTE:\n{chr(10).join(r[0] for r in conn.execute('SELECT description FROM promises WHERE closed_cycle IS NULL'))}\n\n" +
              (f"FINE DEL CAPITOLO PRECEDENTE:\n{prev[0][-1200:]}\n" if prev else ""))
    chapter = provider.complete("novelist", _prompt("novelist"), nov_in)
    review, rounds = {"ok": False, "issues": []}, 0
    while True:
        issues = lint(chapter)
        ed = parse_json(provider.complete("continuity", _prompt("continuity_editor"),
              f"CAPITOLO:\n{chapter}\n\nEVENTI CANONICI:\n{cyc_events}\n\n{C.canon_summary(conn)}\n\nCONOSCENZE PER POV:\n{C.pov_knowledge(conn, povs)}"))
        issues += ed.get("issues", [])
        claims = AD.review(provider, _prompt, AD.extract_claims(chapter))
        issues += [{"tipo": "dato", "citazione": c["context"], "correzione": c["correction"] or c["advisor_note"]} for c in claims if c["verdict"] == "correggere"]
        review = {"ok": not issues, "issues": issues}
        if not issues or rounds >= max_revisions: break
        rounds += 1
        chapter = provider.complete("novelist", _prompt("novelist"), nov_in + "\n\nREVISIONE RICHIESTA. Correggi questi problemi e riscrivi tutto il capitolo:\n" +
                                    json.dumps(issues, ensure_ascii=False, indent=1))
    AD.save_claims(conn, cycle, claims)
    note = "" if review["ok"] else "<!-- REVIEW: problemi residui -->\n" + "\n".join(f"<!-- {i['tipo']}: {i['citazione']} -> {i['correzione']} -->" for i in review["issues"]) + "\n"
    conn.execute("INSERT OR REPLACE INTO chapters(cycle,version,body_md,status) VALUES(?,1,?,'bozza')", (cycle, note + chapter))
    conn.commit(); conn.close()
    return {"status": "bozza", "cycle": cycle, "revisioni": rounds, "ok_editor": review["ok"], "problemi": review["issues"],
            "ops_applicate": len(ops_ok), "ops_rifiutate": ops_bad, "eventi": ids,
            "piano_scene": len(plan["scene_plan"]), "piano_scarti": plot_scarti, "avvisi_trama": plot_avvisi,
            "affermazioni_tecniche": len(claims), "da_correggere": sum(c["verdict"] == "correggere" for c in claims)}

def clean_chapter(md):
    md = re.sub(r"<!--.*?-->\n?", "", md, flags=re.S)
    return re.sub(r"[ \t]*\[\[VERIFICA:.*?\]\]", "", md, flags=re.S).strip() + "\n"

def unverified_count(db_path):
    if not os.path.exists(db_path): return 0
    c = DB.connect(db_path)
    row = c.execute("SELECT MAX(cycle) FROM chapters WHERE status='bozza'").fetchone()[0]
    n = c.execute("SELECT COUNT(*) FROM tech_claims WHERE cycle=? AND status='non_verificato'", (row,)).fetchone()[0] if row else 0
    c.close(); return n

def approve(base_db, draft_db, out_dir):
    if not os.path.exists(draft_db): raise RuntimeError("nessuna bozza da approvare")
    conn = DB.connect(draft_db)
    row = conn.execute("SELECT cycle,body_md FROM chapters WHERE status='bozza' ORDER BY cycle DESC LIMIT 1").fetchone()
    if not row: raise RuntimeError("nessuna bozza da approvare")
    cycle, body = row
    conn.execute("UPDATE chapters SET status='approvato' WHERE cycle=?", (cycle,)); conn.commit()
    claims = conn.execute("SELECT domain,context,verdict,advisor_note,correction,search_hint,status,source_url FROM tech_claims WHERE cycle=? ORDER BY id", (cycle,)).fetchall()
    conn.close()
    shutil.copy(draft_db, base_db); os.remove(draft_db)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"capitolo_{cycle:02d}.md")
    open(path, "w", encoding="utf-8").write(clean_chapter(body))
    if claims:
        L = [f"# Verifiche tecniche — capitolo {cycle}", "", "Il giudizio dell'advisor e una valutazione di plausibilita, non una verifica. Solo lo stato 'verificato' indica un controllo umano su una fonte.", ""]
        for d, ctx, v, note, corr, hint, st, url in claims:
            L += [f"- **[{st}]** ({d}) {ctx}", f"  - giudizio advisor: {v}" + (f" — {note}" if note else ""), *( [f"  - correzione suggerita: {corr}"] if corr else []),
                  *( [f"  - da cercare: {hint}"] if hint else []), *( [f"  - fonte: {url}"] if url else [])]
        open(os.path.join(out_dir, f"capitolo_{cycle:02d}.verifiche.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return path

def reject(draft_db):
    if os.path.exists(draft_db): os.remove(draft_db)
