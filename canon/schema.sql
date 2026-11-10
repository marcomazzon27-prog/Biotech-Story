PRAGMA foreign_keys = ON;

CREATE TABLE entities (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('persona','org','luogo','oggetto')),
  name TEXT NOT NULL, role TEXT, tier TEXT CHECK(tier IN ('main','sec',NULL)),
  place TEXT, attrs_json TEXT DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'vivo', died_cycle INTEGER
);
CREATE TABLE stats (
  entity_id TEXT NOT NULL REFERENCES entities(id), stat TEXT NOT NULL,
  value INTEGER NOT NULL CHECK(value BETWEEN 0 AND 10), PRIMARY KEY(entity_id, stat)
);
CREATE TABLE relations (
  a TEXT NOT NULL REFERENCES entities(id), b TEXT NOT NULL REFERENCES entities(id),
  type TEXT NOT NULL CHECK(type IN ('family','business','conflict','romance','secret','knowledge')),
  label TEXT, strength INTEGER NOT NULL CHECK(strength BETWEEN 0 AND 10),
  valid_from INTEGER NOT NULL DEFAULT 0, valid_to INTEGER, PRIMARY KEY(a,b,type)
);
CREATE TABLE events (
  id TEXT PRIMARY KEY, cycle INTEGER NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
  actor TEXT REFERENCES entities(id), cause_event_id TEXT REFERENCES events(id),
  location TEXT, description TEXT, effects_json TEXT DEFAULT '{}', seed TEXT, origin TEXT NOT NULL DEFAULT 'engine'
);
CREATE TABLE facts (
  id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL,
  is_true INTEGER NOT NULL DEFAULT 1, created_cycle INTEGER NOT NULL
);
CREATE TABLE knowledge (
  entity_id TEXT NOT NULL REFERENCES entities(id), fact_id TEXT NOT NULL REFERENCES facts(id),
  certainty TEXT NOT NULL CHECK(certainty IN ('sa','sospetta','crede_falso')),
  learned_cycle INTEGER NOT NULL, from_entity TEXT, PRIMARY KEY(entity_id, fact_id)
);
CREATE TABLE secrets (fact_id TEXT PRIMARY KEY REFERENCES facts(id), protected_by TEXT, risk_if_exposed TEXT);
CREATE TABLE promises (
  id TEXT PRIMARY KEY, description TEXT NOT NULL, opened_cycle INTEGER NOT NULL, closed_cycle INTEGER
);
CREATE TABLE chapters (
  cycle INTEGER NOT NULL, version INTEGER NOT NULL DEFAULT 1, body_md TEXT,
  status TEXT NOT NULL DEFAULT 'bozza' CHECK(status IN ('bozza','approvato')), PRIMARY KEY(cycle, version)
);
CREATE TABLE cycles (cycle INTEGER PRIMARY KEY, seed TEXT NOT NULL);
