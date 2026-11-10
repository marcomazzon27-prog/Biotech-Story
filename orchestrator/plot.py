"""Plot Architect (parte deterministica): debiti narrativi, foreshadowing, budget dei twist."""
OVERDUE_AFTER = 4     # una promessa aperta da >= 4 cicli e "in ritardo"
TWIST_COOLDOWN = 3    # al massimo un twist ogni 3 cicli
MAX_DUE = 8

def debt_report(conn, cycle):
    promises = [dict(id=i, description=d, opened=o, age=cycle - o, overdue=(cycle - o) >= OVERDUE_AFTER)
                for i, d, o in conn.execute("SELECT id,description,opened_cycle FROM promises WHERE closed_cycle IS NULL ORDER BY opened_cycle")]
    notes = [dict(id=i, description=d, planted=c, due=due, late=(due is not None and due < cycle))
             for i, d, c, due in conn.execute("SELECT id,description,cycle,due_cycle FROM plot_notes WHERE kind='foreshadow' AND resolved_cycle IS NULL AND (due_cycle IS NULL OR due_cycle<=?) ORDER BY due_cycle", (cycle + 1,))]
    last = conn.execute("SELECT MAX(cycle) FROM plot_notes WHERE kind='twist'").fetchone()[0]
    return dict(promises=promises, notes=notes, last_twist=last, twist_allowed=(last is None or cycle - last >= TWIST_COOLDOWN))

def format_report(r):
    L = ["PROMESSE APERTE:"] + [f"- [{p['id']}] {p['description']} (aperta da {p['age']} cicli{' — IN RITARDO' if p['overdue'] else ''})" for p in r["promises"]]
    L += ["FORESHADOWING DA PAGARE:"] + ([f"- nota {n['id']}: {n['description']} (scadenza ciclo {n['due']}{', SCADUTA' if n['late'] else ''})" for n in r["notes"]] or ["- nessuno"])
    L.append("TWIST: " + ("consentito" if r["twist_allowed"] else f"NON consentito (ultimo al ciclo {r['last_twist']})"))
    return "\n".join(L)

def validate_plan(conn, cycle, plan, actors):
    """Restituisce (piano_pulito, scarti, avvisi). Nulla di invalido entra nel canone."""
    scarti, avvisi = [], []
    ev_ids = {r[0] for r in conn.execute("SELECT id FROM events WHERE cycle=?", (cycle,))}
    open_p = {r[0] for r in conn.execute("SELECT id FROM promises WHERE closed_cycle IS NULL")}
    scenes = []
    for s in plan.get("scene_plan", []):
        if s.get("pov") not in actors or s.get("evento_id") not in ev_ids or not str(s.get("scopo", "")).strip():
            scarti.append({"scena": s, "motivo": "pov, evento o scopo non validi"}); continue
        av = [p for p in s.get("avanza", []) if p in open_p]
        scarti += [{"promessa": p, "motivo": "non aperta"} for p in s.get("avanza", []) if p not in open_p]
        scenes.append(dict(pov=s["pov"], evento_id=s["evento_id"], scopo=str(s["scopo"]).strip(), avanza=av))
    if len(scenes) > 5: scarti.append({"motivo": "oltre 5 scene, troncato"}); scenes = scenes[:5]
    if not scenes: avvisi.append("piano_vuoto")
    plant = []
    for p in plan.get("plant", []):
        d = p.get("due_cycle")
        if isinstance(d, int) and cycle < d <= cycle + MAX_DUE and str(p.get("descrizione", "")).strip():
            plant.append(dict(descrizione=str(p["descrizione"]).strip(), due_cycle=d))
        else: scarti.append({"seme": p, "motivo": "scadenza o descrizione non valida"})
    valid_notes = {r[0] for r in conn.execute("SELECT id FROM plot_notes WHERE kind='foreshadow' AND resolved_cycle IS NULL")}
    payoff = [n for n in plan.get("payoff", []) if n in valid_notes]
    scarti += [{"payoff": n, "motivo": "nota inesistente o gia pagata"} for n in plan.get("payoff", []) if n not in valid_notes]
    twist = plan.get("twist")
    if twist:
        if not debt_report(conn, cycle)["twist_allowed"] or not str(twist.get("descrizione", "")).strip():
            scarti.append({"twist": twist, "motivo": "budget dei twist esaurito o descrizione vuota"}); twist = None
    advanced = {p for s in scenes for p in s["avanza"]}
    ignored = [p["id"] for p in debt_report(conn, cycle)["promises"] if p["overdue"] and p["id"] not in advanced]
    if ignored: avvisi.append({"debiti_ignorati": ignored})
    return dict(scene_plan=scenes, plant=plant, payoff=payoff, twist=twist), scarti, avvisi

def apply_plan(conn, cycle, plan):
    for p in plan["plant"]:
        conn.execute("INSERT INTO plot_notes(cycle,kind,description,due_cycle) VALUES(?,?,?,?)", (cycle, "foreshadow", p["descrizione"], p["due_cycle"]))
    for n in plan["payoff"]:
        conn.execute("UPDATE plot_notes SET resolved_cycle=? WHERE id=?", (cycle, n))
    if plan["twist"]:
        conn.execute("INSERT INTO plot_notes(cycle,kind,description,resolved_cycle) VALUES(?,?,?,?)", (cycle, "twist", plan["twist"]["descrizione"], cycle))
    conn.commit()

def format_plan(plan):
    L = [f"{i+1}. POV {s['pov']} — evento {s['evento_id']} — scopo: {s['scopo']}" + (f" — fa avanzare: {', '.join(s['avanza'])}" if s["avanza"] else "") for i, s in enumerate(plan["scene_plan"])]
    if plan["twist"]: L.append("TWIST da inserire: " + plan["twist"]["descrizione"])
    L += [f"Semina: {p['descrizione']}" for p in plan["plant"]]
    return "\n".join(L) or "(nessun vincolo: libera impostazione coerente con gli eventi)"
