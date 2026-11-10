"""Motore deterministico di MNEMOSINE.
Il motore PROPONE eventi (puro, riproducibile dal seed); validate() li controlla;
commit() li scrive nel canone. Nessun LLM scrive mai direttamente nel database."""
import json, random, sqlite3

STATS = ("power","money","rep","guilt","bonds","risk","health")
TRAIT_BONUS = {"elia": 1, "arthur": 2, "sofia": 1}

EXTERNAL = [
 dict(name="Indagine regolatoria", weight=5, effect=dict(guilt=1,risk=1), chain="Richiesta di documenti", p=.3),
 dict(name="Offerta M&A", weight=4, effect=dict(power=1,money=1), chain="Guerra di prezzo", p=.4),
 dict(name="Data breach", weight=3, effect=dict(risk=2,rep=-1), chain="Azione legale GDPR", p=.5),
 dict(name="Trial clinico fallisce", weight=3, effect=dict(money=-2,rep=-1), chain="Crollo azionario", p=.6),
 dict(name="Trial clinico riesce", weight=3, effect=dict(rep=2,money=1), chain="Interesse big pharma", p=.5),
 dict(name="Insider trading", weight=3, effect=dict(guilt=2,risk=2), prereq=dict(guilt=4), chain="Fascicolo SEC", p=.5),
 dict(name="Leak sulla stampa", weight=5, effect=dict(rep=-2,risk=1), chain="Crisi reputazionale", p=.4),
 dict(name="Morte sospetta", weight=2, effect=dict(guilt=2,risk=2), prereq=dict(risk=4), lethal=True, chain="Eredita contesa", p=.5),
 dict(name="Fondo sovrano entra", weight=3, effect=dict(money=2,power=-1), chain="Due diligence IP", p=.5),
 dict(name="Crisi di liquidita", weight=4, effect=dict(money=-2,risk=2), prereq=dict(money=5), chain="Royalty monetization", p=.4),
 dict(name="Cambio normativo", weight=3, effect=dict(risk=1,rep=1), chain="Adeguamento forzato", p=.3),
 dict(name="Epidemia locale", weight=2, effect=dict(health=-2,rep=1), chain="Paura sanitaria", p=.4),
]
PERSONAL = [
 dict(name="Ricatto", weight=4, effect=dict(guilt=1,risk=2)),
 dict(name="Alleanza inattesa", weight=5, effect=dict(bonds=2,power=1)),
 dict(name="Tradimento", weight=4, effect=dict(bonds=-2,guilt=1)),
 dict(name="Malattia", weight=3, effect=dict(health=-2,bonds=1)),
 dict(name="Debito", weight=4, effect=dict(money=-1,risk=1)),
 dict(name="Seduzione", weight=4, effect=dict(bonds=2,risk=1)),
 dict(name="Lutto", weight=3, effect=dict(guilt=2,bonds=-1)),
 dict(name="Scoperta scientifica", weight=3, effect=dict(rep=2,risk=1)),
]
CONSEQUENCES = [
 dict(label="+Potere -Reputazione", apply=dict(power=1,rep=-1)),
 dict(label="+Soldi +Rischio", apply=dict(money=1,risk=1)),
 dict(label="-Soldi +Legame", apply=dict(money=-1,bonds=1)),
 dict(label="+Colpa -Salute", apply=dict(guilt=1,health=-1)),
 dict(label="+Influenza -Privacy", apply=dict(power=1,risk=1)),
 dict(label="+Scoperta +Invidia", apply=dict(rep=1,risk=1,guilt=1)),
]

def clamp(v): return max(0, min(10, v))

def _weighted(rng, items):
    total = sum(i.get("weight", 1) for i in items)
    r = rng.random() * total
    for it in items:
        r -= it.get("weight", 1)
        if r <= 0: return it
    return items[-1]

def _stats(conn, eid):
    return {s: v for s, v in conn.execute("SELECT stat,value FROM stats WHERE entity_id=?", (eid,))}

def _ok(stats, prereq): return all(stats[k] >= v for k, v in (prereq or {}).items())

def current_cycle(conn):
    return conn.execute("SELECT COALESCE(MAX(cycle),0) FROM cycles").fetchone()[0]

def _victim(conn, rng, actor):
    """La vittima deve avere un legame (conflict/secret/business, forza>0) con l'attore ed essere viva."""
    rows = conn.execute("""
      SELECT e.id, r.strength FROM relations r JOIN entities e
        ON e.id = CASE WHEN r.a=? THEN r.b ELSE r.a END
      WHERE (r.a=? OR r.b=?) AND r.type IN ('conflict','secret','business') AND r.strength>0
        AND e.status='vivo' AND e.tier='sec' AND e.kind='persona' ORDER BY e.id""", (actor,actor,actor)).fetchall()
    if not rows: return None
    return _weighted(rng, [dict(id=i, weight=s) for i, s in rows])["id"]

def propose_cycle(conn, base_seed="mnemosine"):
    """Funzione pura: legge il canone, non scrive nulla. Stesso seed + stesso canone => stesso output."""
    cycle = current_cycle(conn) + 1
    seed = f"{base_seed}:{cycle}"
    rng = random.Random(seed)
    events, deltas = [], {}
    mains = [r[0] for r in conn.execute(
        "SELECT id FROM entities WHERE tier='main' AND status='vivo' ORDER BY id")]
    for actor in mains:
        st = _stats(conn, actor)
        ext = _weighted(rng, [e for e in EXTERNAL if _ok(st, e.get("prereq"))])
        pers = _weighted(rng, PERSONAL)
        cons = _weighted(rng, CONSEQUENCES)
        react = rng.randint(1,6) + rng.randint(1,6) + TRAIT_BONUS.get(actor,0) + (st["risk"] - st["health"])
        eff = {}
        for src in (ext["effect"], pers["effect"], cons["apply"]):
            for k, v in src.items(): eff[k] = eff.get(k, 0) + v
        n = len(events)
        main_ev = dict(idx=n, cycle=cycle, actor=actor, kind="esterno", name=ext["name"], cause=None,
                       personal=pers["name"], consequence=cons["label"], reaction=react, effects=eff, victim=None)
        if ext.get("lethal"):
            main_ev["victim"] = _victim(conn, rng, actor)
        events.append(main_ev)
        for k, v in eff.items(): deltas.setdefault(actor, {}); deltas[actor][k] = deltas[actor].get(k, 0) + v
        if rng.random() < ext["p"]:  # catena: l'evento figlio punta alla causa
            events.append(dict(idx=n+1, cycle=cycle, actor=actor, kind="catena", name=ext["chain"], cause=n,
                               personal=None, consequence=None, reaction=None, effects={}, victim=None))
    return dict(cycle=cycle, seed=seed, events=events)

def validate(conn, proposal):
    """Il World Keeper (codice) rifiuta le proposte incoerenti."""
    if proposal["cycle"] != current_cycle(conn) + 1:
        raise ValueError("ciclo non consecutivo")
    for ev in proposal["events"]:
        row = conn.execute("SELECT status FROM entities WHERE id=?", (ev["actor"],)).fetchone()
        if not row or row[0] != "vivo": raise ValueError(f"attore non valido/morto: {ev['actor']}")
        if ev["cause"] is not None and not (0 <= ev["cause"] < ev["idx"]):
            raise ValueError("causa inesistente")
        if ev["victim"]:
            v = conn.execute("SELECT status FROM entities WHERE id=?", (ev["victim"],)).fetchone()
            if not v or v[0] != "vivo": raise ValueError(f"vittima non valida: {ev['victim']}")
        for k in ev["effects"]:
            if k not in STATS: raise ValueError(f"stat sconosciuta: {k}")
    return True

def commit(conn, proposal):
    """Scrive eventi, stat, morti e relazioni chiuse in un'unica transazione."""
    validate(conn, proposal)
    cy, ids = proposal["cycle"], {}
    with conn:
        conn.execute("INSERT INTO cycles VALUES(?,?)", (cy, proposal["seed"]))
        for ev in proposal["events"]:
            eid = f"c{cy:02d}-{ev['idx']:02d}"; ids[ev["idx"]] = eid
            cause = ids.get(ev["cause"]) if ev["cause"] is not None else None
            desc = ev["name"] + (f" | {ev['personal']} | {ev['consequence']} | reazione {ev['reaction']}" if ev["personal"] else "")
            conn.execute("INSERT INTO events(id,cycle,kind,name,actor,cause_event_id,description,effects_json,seed,origin) "
                         "VALUES(?,?,?,?,?,?,?,?,?,'engine')",
                         (eid, cy, ev["kind"], ev["name"], ev["actor"], cause, desc, json.dumps(ev["effects"]), proposal["seed"]))
            for k, v in ev["effects"].items():
                cur = conn.execute("SELECT value FROM stats WHERE entity_id=? AND stat=?", (ev["actor"], k)).fetchone()[0]
                conn.execute("UPDATE stats SET value=? WHERE entity_id=? AND stat=?", (clamp(cur + v), ev["actor"], k))
            if ev["victim"]:
                conn.execute("UPDATE entities SET status='morto', died_cycle=? WHERE id=?", (cy, ev["victim"]))
                conn.execute("UPDATE relations SET strength=0, valid_to=? WHERE a=? OR b=?", (cy, ev["victim"], ev["victim"]))
                conn.execute("INSERT INTO promises(id,description,opened_cycle) VALUES(?,?,?)",
                             (f"p-{eid}", f"Chi e responsabile della morte di {ev['victim']}?", cy))
    return ids
