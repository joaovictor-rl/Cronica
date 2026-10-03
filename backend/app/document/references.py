"""Numeração (seções, figuras, tabelas), \\ref, \\cite e a lista de referências do .bib."""
import re

from app.diff.bib import parse_bib
from app.document.texutils import strip_tex


def split_authors(field: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for match in re.finditer(r"[{}]|\s+and\s+", field):
        token = match.group(0)
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
        elif depth == 0:
            parts.append(field[start:match.start()])
            start = match.end()
    parts.append(field[start:])
    return [p.strip() for p in parts if p.strip()]


def split_name(name: str) -> tuple[str, str]:
    """Separa (prenomes, sobrenome) como o BibTeX: 'Walter de Abreu Cybis' -> ('Walter', 'de Abreu Cybis')."""
    if "," in name:
        last, first = name.split(",", 1)
        return first.strip(), last.strip()
    words = name.split()
    lower = [i for i, w in enumerate(words[:-1]) if w[0].islower()]
    if lower:
        return " ".join(words[:lower[0]]), " ".join(words[lower[0]:])
    return " ".join(words[:-1]), words[-1] if words else ""


def surname(name: str) -> str:
    if name.startswith("{") and name.endswith("}"):
        return strip_tex(name)
    return strip_tex(split_name(name)[1])


def initials(name: str) -> str:
    """'Alves, Vicente Paulo' ou 'Vicente Paulo Alves' -> 'Alves, V. P.'"""
    if name.startswith("{") and name.endswith("}"):
        return strip_tex(name)
    first, last = split_name(name)
    letters = " ".join(w[0] + "." for w in strip_tex(first).replace("-", " ").split() if w)
    return f"{strip_tex(last)}, {letters}" if letters else strip_tex(last)


def cite_label(entry: dict | None, key: str) -> str:
    if not entry:
        return key
    fields = entry["fields"]
    names = split_authors(fields.get("author") or fields.get("editor") or "")
    year = strip_tex(fields.get("year", ""))
    if not names:
        who = strip_tex(fields.get("organization") or fields.get("title", key))
    elif len(names) == 1:
        who = surname(names[0])
    elif len(names) == 2:
        who = f"{surname(names[0])} and {surname(names[1])}"
    else:
        who = f"{surname(names[0])} et al."
    return f"{who} {year}".strip()


def format_entry(entry: dict) -> str:
    """Referência no estilo usado pela SBC (autor-data), em texto simples."""
    f = {k: strip_tex(v) for k, v in entry["fields"].items()}
    names = [initials(n) for n in split_authors(entry["fields"].get("author", ""))]
    if len(names) > 2:
        authors = ", ".join(names[:-1]) + ", and " + names[-1]
    else:
        authors = " and ".join(names) or f.get("organization", "")
    parts = [f"{authors} ({f['year']})." if f.get("year") else f"{authors}."]
    parts.append(f.get("title", "") + ".")
    kind = entry["type"]
    if kind == "article":
        venue = f.get("journal", "")
        if f.get("volume"):
            venue += f", {f['volume']}" + (f"({f['number']})" if f.get("number") else "")
        if f.get("pages"):
            venue += f":{f['pages']}"
        parts.append(venue + ".")
    elif kind in ("inproceedings", "incollection", "conference"):
        venue = "In " + f.get("booktitle", "")
        if f.get("pages"):
            venue += f", pages {f['pages']}"
        if f.get("address"):
            venue += f", {f['address']}"
        parts.append(venue + ".")
        if f.get("publisher"):
            parts.append(f["publisher"] + ".")
    else:
        for field in ("publisher", "organization", "institution", "school", "howpublished"):
            if f.get(field) and f[field] != authors:
                parts.append(f[field] + ".")
        if f.get("address"):
            parts[-1] = parts[-1].rstrip(".") + f", {f['address']}."
    if f.get("url") and "howpublished" not in f:
        parts.append(f["url"])
    if f.get("note"):
        parts.append(f["note"] + ".")
    text = " ".join(p for p in parts if p.strip(". "))
    return re.sub(r"\s+", " ", text).replace("..", ".").strip()


# Estilos do \bibliographystyle que numeram as citações: [1], [2]...
NUMERIC = {"ieeetran", "ieeetr", "unsrt", "unsrtnat", "plain", "abbrv", "acm", "splncs04", "vancouver"}
SORTED_NUMERIC = {"plain", "abbrv", "acm", "splncs04"}  # numeradas em ordem alfabética, não de citação


def citation_style(doc: dict) -> str:
    """'abnt', 'numeric', 'numeric-sorted' ou 'autor-data' (o padrão, usado pela SBC)."""
    if "abntex2cite" in doc.get("preamble", ""):
        return "abnt"
    for block in doc["blocks"]:
        if block["type"] == "hidden" and block.get("kind") == "bibliographystyle":
            found = re.search(r"\{([^}]*)\}", block["src"])
            name = found.group(1).strip().lower() if found else ""
            if name.startswith("abntex2"):
                return "abnt"
            if name in NUMERIC:
                return "numeric-sorted" if name in SORTED_NUMERIC else "numeric"
    return "autor-data"


def name_parts(name: str) -> tuple[str, str, str]:
    """(prenomes, partícula, sobrenome): 'Bruno Santana da Silva' -> ('Bruno Santana', 'da', 'Silva')."""
    first, last = split_name(name)
    words = last.split()
    particles = []
    while len(words) > 1 and words[0][:1].islower():
        particles.append(words.pop(0))
    return strip_tex(first), strip_tex(" ".join(particles)), strip_tex(" ".join(words))


def abnt_cite(entry: dict | None, key: str, inline: bool) -> str:
    """ABNT: (BARBOSA; SILVA, 2010) entre parênteses, ou Barbosa e Silva (2010) dentro da frase."""
    if not entry:
        return key
    fields = entry["fields"]
    names = split_authors(fields.get("author") or fields.get("editor") or "")
    year = strip_tex(fields.get("year", ""))
    if not names:
        who = [strip_tex(fields.get("organization") or fields.get("title", key))]
    else:
        who = [n[1:-1] if n.startswith("{") else name_parts(n)[2] for n in names]
        who = [strip_tex(w) for w in who]
        if len(who) > 3:
            who = [who[0] + " et al."]
    if inline:
        return f"{' e '.join(who)} ({year})"
    return f"{'; '.join(w.upper().replace(' ET AL.', ' et al.') for w in who)}, {year}"


def format_abnt(entry: dict) -> str:
    f = {k: strip_tex(v) for k, v in entry["fields"].items()}
    people = []
    for name in split_authors(entry["fields"].get("author", "")):
        if name.startswith("{"):
            people.append(strip_tex(name).upper())
            continue
        first, particle, last = name_parts(name)
        people.append(f"{last.upper()}, {first}{' ' + particle if particle else ''}".strip(", "))
    if len(people) > 3:
        people = [people[0] + " et al"]
    authors = "; ".join(people) or f.get("organization", "").upper()
    parts = [authors + ".", f.get("title", "") + "."]
    kind = entry["type"]
    if kind == "article":
        venue = f.get("journal", "")
        for field, label in (("volume", "v."), ("number", "n."), ("pages", "p.")):
            if f.get(field):
                venue += f", {label} {f[field]}"
        parts.append(f"{venue}, {f.get('year', '')}.")
    elif kind in ("inproceedings", "incollection", "conference"):
        parts.append(f"In: {f.get('booktitle', '')}.")
        place = ": ".join(x for x in (f.get("address"), f.get("publisher")) if x)
        parts.append(f"{place + ', ' if place else ''}{f.get('year', '')}." + (f" p. {f['pages']}." if f.get("pages") else ""))
    else:
        if f.get("edition"):
            parts.append(f"{f['edition']}. ed.")
        place = ": ".join(x for x in (f.get("address"), f.get("publisher") or f.get("institution") or f.get("school")) if x)
        parts.append(f"{place + ', ' if place else ''}{f.get('year', '')}.")
    if f.get("url"):
        parts.append(f"Disponível em: {f['url']}.")
    text = " ".join(p for p in parts if p.strip(". ,"))
    return re.sub(r"\s+", " ", text).replace("..", ".").strip()


def format_numbered(entry: dict) -> str:
    """Estilo do IEEE: iniciais antes do sobrenome e o título entre aspas."""
    f = {k: strip_tex(v) for k, v in entry["fields"].items()}
    people = []
    for name in split_authors(entry["fields"].get("author", "")):
        if name.startswith("{"):
            people.append(strip_tex(name))
            continue
        first, particle, last = name_parts(name)
        letters = " ".join(w[0] + "." for w in first.replace("-", " ").split())
        people.append(" ".join(x for x in (letters, particle, last) if x))
    authors = ", ".join(people[:-1]) + (", and " if len(people) > 2 else " and ") + people[-1] if len(people) > 1 else "".join(people)
    kind = entry["type"]
    if kind == "article":
        rest = f"“{f.get('title', '')},” {f.get('journal', '')}" + (f", vol. {f['volume']}" if f.get("volume") else "") \
            + (f", no. {f['number']}" if f.get("number") else "") + (f", pp. {f['pages']}" if f.get("pages") else "") + f", {f.get('year', '')}."
    elif kind in ("inproceedings", "incollection", "conference"):
        rest = f"“{f.get('title', '')},” in {f.get('booktitle', '')}, {f.get('year', '')}" + (f", pp. {f['pages']}" if f.get("pages") else "") + "."
    else:
        place = ": ".join(x for x in (f.get("address"), f.get("publisher")) if x)
        rest = f"{f.get('title', '')}." + (f" {place}," if place else "") + f" {f.get('year', '')}."
    return re.sub(r"\s+", " ", f"{authors + ', ' if authors else ''}{rest}").strip()


def entry_label(entry: dict, key: str, style: str, number: int | None = None) -> str:
    """Como a citação aparece no texto, no estilo do artigo."""
    if style.startswith("numeric"):
        return f"[{number}]" if number else "[?]"
    if style == "abnt":
        return f"({abnt_cite(entry, key, inline=False)})"
    return f"[{cite_label(entry, key)}]"


def entry_text(entry: dict, style: str) -> str:
    return {"abnt": format_abnt, "numeric": format_numbered, "numeric-sorted": format_numbered}.get(style, format_entry)(entry)


def load_bibliography(doc: dict, main_path: str, files: dict[str, bytes]) -> dict:
    folder = main_path.rsplit("/", 1)[0] + "/" if "/" in main_path else ""
    wanted = [b for block in doc["blocks"] if block["type"] == "references" for b in block.get("files", [])]
    paths = [folder + (name if name.endswith(".bib") else name + ".bib") for name in wanted]
    paths = [p for p in paths if p in files] or [p for p in files if p.endswith(".bib")]
    entries = {}
    for path in paths:
        entries.update(parse_bib(files[path].decode("utf-8", "replace")))
    return entries


def walk_spans(doc: dict):
    for field in doc.get("meta", {}).values():
        yield from field["spans"]
    for block in doc["blocks"]:
        for spans in block_span_lists(block):
            yield from spans


def block_span_lists(block: dict):
    kind = block["type"]
    if kind in ("paragraph", "heading"):
        yield block["spans"]
    elif kind == "list":
        for item in block["items"]:
            yield item["spans"]
    elif kind == "abstract":
        yield from block["paragraphs"]
    elif kind in ("figure", "table"):
        if block.get("caption"):
            yield block["caption"]
        for image in block.get("images", []):
            if image.get("caption"):
                yield image["caption"]
        for row in block.get("rows", []):
            yield from row
        if block.get("note"):
            yield block["note"]


def annotate(doc: dict, bib: dict) -> dict:
    """Preenche números de seção/figura/tabela, o texto dos \\ref e \\cite, e a lista de referências."""
    labels = {}
    counters = [0, 0, 0, 0, 0]
    figures = tables = 0
    last_number = None
    for block in doc["blocks"]:
        kind = block["type"]
        if kind == "heading" and not block.get("star") and 1 <= block.get("level", 1) <= 3:
            level = block["level"]
            counters[level] += 1
            for deeper in range(level + 1, len(counters)):
                counters[deeper] = 0
            block["number"] = ".".join(str(counters[i]) for i in range(1, level + 1))
            last_number = block["number"]
        elif kind == "hidden" and block.get("kind") == "label" and block.get("key") and last_number:
            labels[block["key"]] = last_number
        elif kind == "figure":
            figures += 1
            block["number"] = str(figures)
            last_number = block["number"]
        elif kind == "table" and block.get("caption"):
            tables += 1
            block["number"] = str(tables)
            last_number = block["number"]
        if kind in ("figure", "table") and block.get("label"):
            labels[block["label"]] = block.get("number", "??")

    style = citation_style(doc)
    cited = []
    for span in walk_spans(doc):
        if span.get("kind") == "cite":
            for key in span.get("keys", []):
                if key not in cited:
                    cited.append(key)
    keys = list(bib) if "*" in cited else [k for k in cited if k in bib]
    if style == "numeric":
        entries = keys  # na ordem em que aparecem no texto
    elif style == "abnt":
        entries = sorted(keys, key=lambda k: format_abnt(bib[k]).lower())
    else:
        entries = sorted(keys, key=lambda k: cite_label(bib[k], k).lower())
    numbers = {k: i + 1 for i, k in enumerate(entries)}

    footnotes = 0
    for span in walk_spans(doc):
        if span.get("kind") == "ref":
            span["label"] = labels.get(span.get("key"), "??")
        elif span.get("kind") == "cite":
            keys_here = span.get("keys", [])
            if span["raw"].startswith("\\nocite"):
                span["label"] = ""
            elif style.startswith("numeric"):
                span["label"] = "[" + ", ".join(str(numbers.get(k, "?")) for k in keys_here) + "]"
            elif style == "abnt":
                inline = span["raw"].startswith(("\\citeonline", "\\citet", "\\citeauthor"))
                parts = [abnt_cite(bib.get(k), k, inline) for k in keys_here]
                span["label"] = "; ".join(parts) if inline else "(" + "; ".join(parts) + ")"
            else:
                span["label"] = "[" + ", ".join(cite_label(bib.get(k), k) for k in keys_here) + "]"
        elif span.get("kind") == "footnote":
            footnotes += 1
            span["label"] = str(footnotes)

    formatter = {"abnt": format_abnt, "numeric": format_numbered, "numeric-sorted": format_numbered}.get(style, format_entry)
    doc["bibliography"] = [
        {"key": k, "text": formatter(bib[k]), **({"number": numbers[k]} if style.startswith("numeric") else {})}
        for k in entries
    ]
    english = doc.get("language") == "en" and not re.search(r"brazil|portug", doc.get("preamble", ""))
    doc["references_title"] = "References" if english else "Referências"
    doc["citation_style"] = style
    return doc
