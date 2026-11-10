CREATE TABLE IF NOT EXISTS plot_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, cycle INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('foreshadow','twist')), description TEXT NOT NULL,
  due_cycle INTEGER, resolved_cycle INTEGER
);
CREATE TABLE IF NOT EXISTS tech_claims (
  id INTEGER PRIMARY KEY AUTOINCREMENT, cycle INTEGER NOT NULL, domain TEXT NOT NULL,
  context TEXT NOT NULL, marker_note TEXT, verdict TEXT NOT NULL DEFAULT 'incerto',
  advisor_note TEXT, correction TEXT, search_hint TEXT,
  status TEXT NOT NULL DEFAULT 'non_verificato' CHECK(status IN ('non_verificato','verificato','corretto','fittizio')),
  source_url TEXT, verified_at TEXT
);
