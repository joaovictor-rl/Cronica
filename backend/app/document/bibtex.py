"""Escrever o arquivo .bib a partir das referências editadas no site.

O cuidado é o mesmo do .tex: uma referência que não mudou é escrita exatamente como estava no arquivo,
e comentários, @string e @preamble ficam onde estavam. Só referências novas ou alteradas são formatadas.
"""
import re
import unicodedata

from app.diff.bib import (
    ENTRY_START,
    SKIP_TYPES,
    matching_close,
    parse_bib,
    parse_fields,
)

TYPES = {
    "article": "Artigo de revista",
    "inproceedings": "Trabalho em evento (anais)",
    "book": "Livro",
    "incollection": "Capítulo de livro",
    "phdthesis": "Tese de doutorado",
    "mastersthesis": "Dissertação de mestrado",
    "misc": "Site ou outro",
    "techreport": "Relatório técnico",
}
FIELD_ORDER = [
    "author", "title", "journal", "booktitle", "editor", "edition", "volume", "number", "pages",
    "publisher", "school", "institution", "organization", "address", "year", "month", "doi", "url",
    "urlaccessdate", "note",
]


def chunks(text: str) -> list[dict]:
    """Divide o .bib em pedaços: referências (com chave) e o resto (comentários, @string...), na ordem do arquivo."""
    out, pos = [], 0
    for match in ENTRY_START.finditer(text):
        if match.start() < pos:
            continue
        if match.start() > pos:
            out.append({"raw": text[pos:match.start()]})
        close = matching_close(text, match.end() - 1)
        raw = text[match.start(): close + 1]
        kind = match.group(1).lower()
        if kind in SKIP_TYPES:
            out.append({"raw": raw})
        else:
            key, _, body = text[match.end(): close].partition(",")
            out.append({"raw": raw, "key": key.strip(), "type": kind, "fields": parse_fields(body)})
        pos = close + 1
    if pos < len(text):
        out.append({"raw": text[pos:]})
    return out


def escape_value(value: str) -> str:
    # Chaves sem par quebrariam o arquivo inteiro; o resto (acentos, LaTeX) fica como a pessoa escreveu.
    depth = 0
    for char in value:
        depth += {"{": 1, "}": -1}.get(char, 0)
        if depth < 0:
            break
    if depth != 0:
        value = value.replace("{", "").replace("}", "")
    return value


def format_entry(entry: dict) -> str:
    fields = {k: v for k, v in entry["fields"].items() if str(v).strip()}
    names = sorted(fields, key=lambda f: (FIELD_ORDER.index(f) if f in FIELD_ORDER else len(FIELD_ORDER), f))
    width = max((len(n) for n in names), default=0)
    lines = [f"  {name.ljust(width)} = {{{escape_value(' '.join(str(fields[name]).split()))}}}" for name in names]
    return f"@{entry['type']}{{{entry['key']},\n" + ",\n".join(lines) + "\n}"


def write_bib(original: str, entries: list[dict]) -> str:
    """O novo .bib: referências na ordem pedida, reaproveitando o texto original das que não mudaram."""
    old = chunks(original)
    old_by_key = {c["key"]: c for c in old if "key" in c}
    kept_other = [c["raw"] for c in old if "key" not in c and c["raw"].strip()]
    parts = [raw.strip() for raw in kept_other]
    for entry in entries:
        before = old_by_key.get(entry["key"])
        same = before and before["type"] == entry["type"] and before["fields"] == normalized(entry["fields"])
        parts.append(before["raw"] if same else format_entry(entry))
    return "\n\n".join(parts) + "\n" if parts else ""


def normalized(fields: dict) -> dict:
    return {k.lower(): " ".join(str(v).split()) for k, v in fields.items() if str(v).strip()}


def ascii_word(text: str) -> str:
    text = re.sub(r"\\[a-zA-Z]+|[{}\\]", "", text)
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower())


STOPWORDS = {"a", "o", "as", "os", "um", "uma", "de", "da", "do", "the", "an", "of", "on", "in", "e", "and", "para", "for"}


def make_key(fields: dict, taken: set[str]) -> str:
    """Chave legível, como barbosa2010interacao, sem repetir as que já existem."""
    from app.document.references import name_parts, split_authors

    authors = split_authors(fields.get("author") or fields.get("editor") or "")
    who = ascii_word(name_parts(authors[0])[2]) if authors else ascii_word(fields.get("organization", ""))[:12]
    year = re.sub(r"\D", "", fields.get("year", ""))[:4]
    words = [ascii_word(w) for w in fields.get("title", "").split()]
    word = next((w for w in words if w and w not in STOPWORDS), "")
    base = (who or "ref") + year + word[:12]
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}{chr(96 + n) if n <= 26 else n}"
    return key


def clean_entries(entries: list[dict]) -> list[dict]:
    """Valida o que veio do site: tipo conhecido, campos simples, chaves únicas e válidas."""
    out, taken = [], set()
    for entry in entries:
        kind = str(entry.get("type", "misc")).lower()
        fields = normalized({str(k).lower(): v for k, v in (entry.get("fields") or {}).items() if re.fullmatch(r"[a-z][a-z0-9_:-]*", str(k).lower())})
        key = str(entry.get("key") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_:.\-+/]+", key) or key in taken:
            key = make_key(fields, taken)
        taken.add(key)
        out.append({"key": key, "type": kind if re.fullmatch(r"[a-z]+", kind) else "misc", "fields": fields})
    return out


def entries_from_bibtex(text: str, taken: set[str]) -> list[dict]:
    """Referências coladas (do Google Acadêmico, por exemplo). Chaves repetidas ganham outra."""
    found = []
    for key, entry in parse_bib(text).items():
        if key in taken or not re.fullmatch(r"[A-Za-z0-9_:.\-+/]+", key):
            key = make_key(entry["fields"], taken)
        taken.add(key)
        found.append({"key": key, "type": entry["type"], "fields": entry["fields"]})
    return found
