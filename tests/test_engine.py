import os, sys, sqlite3, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from canon.seed import build
from engine import engine as E

def fresh(): return build(":memory:") if False else _mem()
def _mem():
    import tempfile
    p = tempfile.mktemp(suffix=".db"); c = build(p); return c

class T(unittest.TestCase):
    def test_seed_storico(self):
        c = _mem()
        self.assertEqual(E.current_cycle(c), 5)
        dead = {r[0] for r in c.execute("SELECT id FROM entities WHERE status='morto'")}
        self.assertEqual(dead, {"marco","croft","hale"})
        orphan = c.execute("SELECT COUNT(*) FROM events WHERE cause_event_id IS NOT NULL AND cause_event_id NOT IN (SELECT id FROM events)").fetchone()[0]
        self.assertEqual(orphan, 0)

    def test_determinismo(self):
        a, b = _mem(), _mem()
        self.assertEqual(E.propose_cycle(a,"s1"), E.propose_cycle(b,"s1"))
        self.assertNotEqual(E.propose_cycle(a,"s1"), E.propose_cycle(a,"s2"))

    def test_prerequisiti_e_catene(self):
        c = _mem()
        for seed in range(200):
            p = E.propose_cycle(c, f"x{seed}")
            for ev in p["events"]:
                if ev["name"] == "Insider trading":
                    self.assertGreaterEqual(E._stats(c, ev["actor"])["guilt"], 4)
                if ev["kind"] == "catena": self.assertLess(ev["cause"], ev["idx"])

    def test_morti_non_agiscono_e_vittime_valide(self):
        c = _mem()
        for seed in range(300):
            p = E.propose_cycle(c, f"y{seed}")
            self.assertTrue(E.validate(c, p))
            for ev in p["events"]:
                self.assertNotIn(ev["actor"], {"marco","croft","hale"})
                self.assertNotIn(ev["victim"], {"marco","croft","hale"})

    def test_commit_e_stat_nei_limiti(self):
        c = _mem()
        for i in range(25):
            E.commit(c, E.propose_cycle(c, "long"))
        self.assertEqual(E.current_cycle(c), 30)
        mn, mx = c.execute("SELECT MIN(value),MAX(value) FROM stats").fetchone()
        self.assertTrue(0 <= mn and mx <= 10)
        # ogni evento di catena ha una causa esistente
        bad = c.execute("SELECT COUNT(*) FROM events WHERE kind='catena' AND cause_event_id IS NULL").fetchone()[0]
        self.assertEqual(bad, 0)
        # ogni morte nuova ha una promessa aperta collegata
        n_dead = c.execute("SELECT COUNT(*) FROM entities WHERE status='morto' AND died_cycle>5").fetchone()[0]
        n_prom = c.execute("SELECT COUNT(*) FROM promises WHERE id LIKE 'p-c%'").fetchone()[0]
        self.assertEqual(n_dead, n_prom)

    def test_validatore_rifiuta(self):
        c = _mem(); p = E.propose_cycle(c, "z")
        p["events"][0]["actor"] = "marco"
        with self.assertRaises(ValueError): E.validate(c, p)
        p = E.propose_cycle(c, "z"); p["cycle"] = 9
        with self.assertRaises(ValueError): E.validate(c, p)

if __name__ == "__main__": unittest.main(verbosity=2)
