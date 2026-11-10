"""Costruisce i contesti per agente. Regola chiave: un Character Agent vede SOLO cio che il personaggio sa."""
import json

def _name(conn, eid):
    r = conn.execute("SELECT name FROM entities WHERE id=?", (eid,)).fetchone(); return r[0] if r else eid

def known_facts(conn, eid):
    return conn.execute("""SELECT f.id,f.subject,f.predicate,f.object,k.certainty FROM knowledge k
        JOIN facts f ON f.id=k.fact_id WHERE k.entity_id=? ORDER BY f.id""", (eid,)).fetchall()

def relations_of(conn, eid):
    out = []
    for a, b, t, l, s in conn.execute("SELECT a,b,type,label,strength FROM relations WHERE (a=? OR b=?) AND strength>0", (eid, eid)):
        o = b if a == eid else a
        st = conn.execute("SELECT status FROM entities WHERE id=?", (o,)).fetchone()
        if st and st[0] == "vivo": out.append(f"- {_name(conn,o)} [{o}]: {t}, {l} (forza {s}/10)")
    return out

def character_context(conn, actor, events, sheet):
    e = conn.execute("SELECT name,role,place FROM entities WHERE id=?", (actor,)).fetchone()
    stats = dict(conn.execute("SELECT stat,value FROM stats WHERE entity_id=?", (actor,)).fetchall())
    kf = known_facts(conn, actor)
    recent = conn.execute("SELECT cycle,name FROM events WHERE actor=? ORDER BY cycle DESC, id DESC LIMIT 4", (actor,)).fetchall()
    lines = [f"PERSONAGGIO: {e[0]} [{actor}] — {e[1]} — {e[2]}", f"SCHEDA: {sheet}", f"STATO (0-10): {json.dumps(stats)}",
             "", "COSA SAI (e solo questo):"]
    lines += [f"- [{i}] {s} {p}: {o} (certezza: {c})" for i, s, p, o, c in kf] or ["- (niente di rilevante)"]
    lines += ["", "RELAZIONI ATTIVE:"] + (relations_of(conn, actor) or ["- (nessuna)"])
    lines += ["", "TUOI ULTIMI EVENTI:"] + [f"- ciclo {c}: {n}" for c, n in reversed(recent)]
    lines += ["", "EVENTI CHE STANNO PER ACCADERE (gia decisi):"]
    for ev in events:
        extra = f" | {ev['personal']} | esito: {ev['consequence']}" if ev["personal"] else ""
        lines.append(f"- {ev['name']}{extra}")
    return "\n".join(lines)

def canon_summary(conn):
    L = ["STATO PROTAGONISTI:"]
    for eid, n in conn.execute("SELECT id,name FROM entities WHERE tier='main'"):
        L.append(f"- {n} [{eid}]: {dict(conn.execute('SELECT stat,value FROM stats WHERE entity_id=?', (eid,)).fetchall())}")
    L.append("MORTI: " + ", ".join(f"{n} (ciclo {c})" for n, c in conn.execute("SELECT name,died_cycle FROM entities WHERE status='morto'")))
    L.append("FATTI E CHI LI CONOSCE:")
    for fid, s, p, o, sec in conn.execute("SELECT f.id,f.subject,f.predicate,f.object,(SELECT 1 FROM secrets WHERE fact_id=f.id) FROM facts f"):
        who = ", ".join(f"{e}:{c}" for e, c in conn.execute("SELECT entity_id,certainty FROM knowledge WHERE fact_id=?", (fid,)))
        L.append(f"- [{fid}]{' (SEGRETO)' if sec else ''} {s} {p}: {o} | conoscono: {who or 'nessuno'}")
    L.append("PROMESSE APERTE:")
    L += [f"- [{i}] {d} (dal ciclo {c})" for i, d, c in conn.execute("SELECT id,description,opened_cycle FROM promises WHERE closed_cycle IS NULL")]
    return "\n".join(L)

def pov_knowledge(conn, povs):
    out = []
    for p in povs:
        out.append(f"{_name(conn,p)} [{p}] sa: " + ("; ".join(f"{s} {pr}: {o} ({c})" for _, s, pr, o, c in known_facts(conn, p)) or "nulla di rilevante"))
    return "\n".join(out)

def cycle_events(conn, cycle):
    rows = conn.execute("""SELECT e.id,e.actor,e.name,e.description,e.location,
        (SELECT name FROM events c WHERE c.id=e.cause_event_id) FROM events e WHERE e.cycle=? ORDER BY e.id""", (cycle,)).fetchall()
    return "\n".join(f"- [{i}] {_name(conn,a)}: {d}" + (f" (causa: {c})" if c else "") for i, a, n, d, l, c in rows)
