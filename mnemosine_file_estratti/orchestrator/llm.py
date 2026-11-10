"""Provider LLM intercambiabili: anthropic (API), manual (copia/incolla in chat), mock (test)."""
import json, os, urllib.request, urllib.error

class Provider:
    def complete(self, role, system, user): raise NotImplementedError

class AnthropicProvider(Provider):
    URL = "https://api.anthropic.com/v1/messages"
    def __init__(self, model=None, max_tokens=4000):
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key: raise RuntimeError("Manca ANTHROPIC_API_KEY")
        self.model = model or os.environ.get("MNEMOSINE_MODEL", "claude-sonnet-5-5")
        self.max_tokens = max_tokens
    def complete(self, role, system, user):
        body = json.dumps({"model": self.model, "max_tokens": self.max_tokens, "system": system,
                           "messages": [{"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(self.URL, data=body, headers={
            "content-type": "application/json", "x-api-key": self.key, "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r: data = json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"API {e.code}: {e.read().decode()[:300]}")
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")

class ManualProvider(Provider):
    """Per chi non ha una chiave API: scrive il prompt in work/, tu lo incolli in una chat Claude
    e salvi la risposta nel file .response.txt indicato."""
    def __init__(self, workdir="work"): self.dir, self.n = workdir, 0; os.makedirs(workdir, exist_ok=True)
    def complete(self, role, system, user):
        self.n += 1; base = os.path.join(self.dir, f"{self.n:02d}_{role}")
        open(base + ".prompt.md", "w", encoding="utf-8").write(f"# ISTRUZIONI (system)\n{system}\n\n# DATI (user)\n{user}\n")
        open(base + ".response.txt", "w", encoding="utf-8").write("")
        input(f"\n[{role}] Incolla {base}.prompt.md in una chat Claude, salva la risposta in\n  {base}.response.txt\nPoi premi INVIO... ")
        txt = open(base + ".response.txt", encoding="utf-8-sig").read().strip()
        if not txt: raise RuntimeError("risposta vuota")
        return txt

class MockProvider(Provider):
    """Risposte deterministiche per i test. overrides[role] = lista di risposte consumate in ordine."""
    def __init__(self, overrides=None): self.overrides, self.calls = {k: list(v) for k, v in (overrides or {}).items()}, []
    def complete(self, role, system, user):
        self.calls.append((role, system, user))
        if self.overrides.get(role): return self.overrides[role].pop(0)
        if role == "character":
            return json.dumps({"azione": "Agisce con cautela.", "intento": "Proteggersi.", "nasconde": [], "mente_a": [], "dialogo_chiave": "Non e come sembra."})
        if role == "world_keeper":
            return json.dumps({"approved": True, "objections": [], "vetoes": [], "ops": [{"op": "open_promise", "description": "Cosa nasconde davvero il ciclo appena chiuso?"}]})
        if role == "novelist":
            return "# Capitolo N — Prova\n\nScena di prova. [[VERIFICA: dato tecnico]]\n"
        if role == "plot_architect":
            return json.dumps({"scene_plan": [], "plant": [], "payoff": [], "twist": None})
        if role in ("advisor_biotech", "advisor_finance"):
            return json.dumps({"verdetti": []})
        if role == "continuity":
            return json.dumps({"ok": True, "issues": []})
        raise ValueError(role)

def make(name):
    return {"anthropic": AnthropicProvider, "manual": ManualProvider, "mock": MockProvider}[name]()
