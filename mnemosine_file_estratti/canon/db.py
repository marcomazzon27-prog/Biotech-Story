import os, sqlite3
HERE = os.path.dirname(os.path.abspath(__file__))
def ensure_schema(conn):
    conn.executescript(open(os.path.join(HERE, "schema_v3.sql"), encoding="utf-8").read())
    conn.commit()
def connect(path):
    """Apre il database e lo porta all'ultimo schema (idempotente: aggiorna anche i DB della Fase 1-2)."""
    conn = sqlite3.connect(path); conn.execute("PRAGMA foreign_keys = ON"); ensure_schema(conn); return conn
