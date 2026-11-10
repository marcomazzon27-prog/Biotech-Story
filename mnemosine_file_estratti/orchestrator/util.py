import json
def parse_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i: raise ValueError("nessun JSON nella risposta")
    return json.loads(text[i:j + 1])
