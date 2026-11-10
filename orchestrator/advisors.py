"""Advisor tecnici: estraggono i marcatori [[VERIFICA: ...]], chiedono un giudizio di PLAUSIBILITA (non una verifica)
e registrano ogni affermazione in tech_claims con stato 'non_verificato' finche un umano non la controlla."""
import re
from orchestrator.util import parse_json

BIO = ("biomarker", "p-tau", "tau", "amiloid", "abeta", "trial", "fase i", "fase ii", "clinic", "ivdr", "crispr", "plasma", "diagnos",
       "sensibilit", "specificit", "ppv", "npv", "cutoff", "pet", "paziente", "genom", "proteina", "laborator")
MARK = re.compile(r"\[\[VERIFICA:\s*(.*?)\]\]", re.S)
VERDICTS = {"ok", "correggere", "incerto"}

def domain_of(text):
    t = text.lower(); return "biotech" if any(k in t for k in BIO) else "finanza"

def extract_claims(text):
    out = []
    for m in MARK.finditer(text):
        seg = text[:m.start()].rstrip(" .\n\t")          # la frase appena prima del marcatore
        start = max(seg.rfind(". ") + 2 if seg.rfind(". ") >= 0 else 0, seg.rfind("\n") + 1)
        ctx = seg[start:].strip() or m.group(1)
        out.append(dict(context=ctx, note=m.group(1).strip(), domain=domain_of(ctx + " " + m.group(1))))
    return out

def review(provider, prompt_loader, claims):
    """Una chiamata per dominio presente. Restituisce i claim arricchiti con verdetto (default: incerto)."""
    for c in claims: c.update(verdict="incerto", advisor_note="", correction=None, search_hint="")
    for domain, role, pname in (("biotech", "advisor_biotech", "advisor_biotech"), ("finanza", "advisor_finance", "advisor_finance")):
        idx = [i for i, c in enumerate(claims) if c["domain"] == domain]
        if not idx: continue
        body = "AFFERMAZIONI DA VALUTARE:\n" + "\n".join(f"{n+1}. {claims[i]['context']}  [nota: {claims[i]['note']}]" for n, i in enumerate(idx))
        res = parse_json(provider.complete(role, prompt_loader(pname), body))
        for v in res.get("verdetti", []):
            n = v.get("id")
            if isinstance(n, int) and 1 <= n <= len(idx):
                c = claims[idx[n - 1]]
                c.update(verdict=v.get("verdetto") if v.get("verdetto") in VERDICTS else "incerto",
                         advisor_note=str(v.get("nota") or ""), correction=(v.get("correzione") or None), search_hint=str(v.get("da_cercare") or ""))
    return claims

def save_claims(conn, cycle, claims):
    conn.execute("DELETE FROM tech_claims WHERE cycle=? AND status='non_verificato'", (cycle,))
    for c in claims:
        conn.execute("INSERT INTO tech_claims(cycle,domain,context,marker_note,verdict,advisor_note,correction,search_hint) VALUES(?,?,?,?,?,?,?,?)",
                     (cycle, c["domain"], c["context"], c["note"], c["verdict"], c["advisor_note"], c["correction"], c["search_hint"]))
    conn.commit()
