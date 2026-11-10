import os, sqlite3
HERE = os.path.dirname(os.path.abspath(__file__))
_ACTIVE_CONNECTIONS = {}

def ensure_schema(conn):
    with open(os.path.join(HERE, "schema_v3.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()

def connect(path):
    """Apre il database e lo porta all'ultimo schema (idempotente: aggiorna anche i DB della Fase 1-2)."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    _ACTIVE_CONNECTIONS[id(conn)] = conn
    ensure_schema(conn)
    return conn

def close_path(path):
    """Chiude le connessioni ancora aperte su un file DB prima di eliminarlo."""
    target = os.path.abspath(path)
    for key, conn in list(_ACTIVE_CONNECTIONS.items()):
        try:
            dbs = conn.execute("PRAGMA database_list").fetchall()
        except sqlite3.Error:
            continue
        if any(os.path.abspath(db_path) == target for _, _, db_path in dbs if db_path):
            try:
                conn.close()
            except sqlite3.Error:
                pass
            finally:
                _ACTIVE_CONNECTIONS.pop(key, None)
