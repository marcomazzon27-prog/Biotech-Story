# MNEMOSINE — Fase 1 (canone + motore deterministico)

Contiene: schema SQLite del canone, import storico dei Cicli 1-5, motore con seed, validatore, test.

## Avvio
    python run.py init        # crea mnemosine.db con i Cicli 1-5
    python run.py propose     # anteprima del Ciclo 6 (non scrive)
    python run.py commit      # scrive il Ciclo 6 nel canone
    python run.py state       # stat, morti, promesse aperte
    python -m unittest discover -s tests -v

## Principi
- Il motore PROPONE, il validatore CONTROLLA, commit() SCRIVE. Gli agenti LLM (Fase 2) useranno solo propose/validate/commit.
- Stesso seed + stesso canone = stesso ciclo (riproducibile e testabile).
- Ogni evento di catena ha `cause_event_id`; ogni morte nuova apre una promessa narrativa e chiude le relazioni.
- Decisioni di canone prese qui: madre di Elia diagnosticata nel 2018, morta nel 2021; Hale morta al Ciclo 2, Marco e Croft al Ciclo 3.

## Prossima fase
Agenti LLM: World Keeper (LLM sopra il validatore), Character Agents con `knowledge`, Novelist + Continuity Editor.

---
# Fase 2 — ciclo assistito (4 agenti + approvazione umana)

Flusso: `propose` → Character Agents (vedono solo cio che il personaggio sa) → World Keeper (veto + operazioni ammesse)
→ `validate/commit` su una COPIA → Novelist ↔ Continuity Editor (max 2 revisioni, con lint deterministico) → bozza.
Il canone vero cambia solo con `approve`.

## Uso
    python run.py draft mock            # prova offline, senza LLM
    python run.py draft manual          # senza chiave API: incolli i prompt di work/ in una chat Claude
    export ANTHROPIC_API_KEY=...        # con chiave API
    python run.py draft anthropic [seed]
    python run.py read                  # leggi il capitolo in bozza
    python run.py approve | reject

## File
- agents/prompts/      prompt di sistema (character, world_keeper, novelist, continuity_editor)
- orchestrator/        llm.py (provider), context.py (contesti con conoscenza limitata), pipeline.py
- compliance/blocklist.txt   nomi reali vietati (il lint blocca il capitolo)
- tests/test_pipeline.py     8 test: bozza isolata, niente fughe di segreti, ops non ammesse rifiutate, veto, revisioni

## Non ancora verificato
Il provider `anthropic` e scritto ma NON e stato eseguito (nessuna chiave nel sandbox): primo test reale da fare in locale.
Marcatori [[VERIFICA: ...]] nel testo = affermazioni tecniche da far controllare al Biotech/Finance Advisor (Fase 3).

---
# Fase 3 — advisor tecnici, Plot Architect, Control Room collegata

## Novita
- **Plot Architect** (`orchestrator/plot.py` + `agents/prompts/plot_architect.md`): prima del Novelist produce un piano scene vincolante.
  Parte deterministica: promesse aperte da >=4 cicli = "in ritardo" (se il piano le ignora, avviso `debiti_ignorati`), foreshadowing con scadenza,
  budget dei twist (max 1 ogni 3 cicli). Ogni voce del piano e validata (pov/evento esistenti, scadenze entro 8 cicli).
- **Advisor Biotech e Finance/Legal** (`orchestrator/advisors.py`): estraggono i marcatori [[VERIFICA: ...]], danno un giudizio di PLAUSIBILITA
  (ok / correggere / incerto) e dicono cosa cercare. Se "correggere", il Novelist riscrive. Ogni affermazione resta `non_verificato`
  finche un umano indica una fonte. Gli advisor non possono inventare fonti: il prompt lo vieta e non esiste un campo per le citazioni.
- **Export pulito**: `approve` scrive `content/capitolo_NN.md` senza marcatori e `capitolo_NN.verifiche.md` con lo stato di ogni affermazione.
- **Control Room collegata** (`server/app.py`, `control_room/index.html`): `python run.py serve` -> http://127.0.0.1:8765
  Mappa causale (eventi e frecce causa-effetto), personaggi con cio che sanno, relazioni, debiti narrativi, verifiche tecniche, capitoli con approva/scarta.
- Sicurezza del server: solo 127.0.0.1, controllo header Host, header X-Mnemosine obbligatorio sui POST, limite 64 KB, URL fonte solo http(s),
  testo del canone sempre escapato nella pagina.

## Comandi nuovi
    python run.py serve [porta]     python run.py claims     python run.py verify <id> <url>

## Cosa NON fa ancora
- Non genera bozze dal browser (si usa `draft` da terminale: il provider manual richiede input interattivo).
- Nessuna verifica automatica di fonti: serve una persona (o, in futuro, un agente con ricerca web e citazioni controllabili).
- Layout non verificato su browser reali (provato solo in jsdom: nessun errore JS, comportamento corretto).
- Modelli e prompt mai provati con un LLM reale.
