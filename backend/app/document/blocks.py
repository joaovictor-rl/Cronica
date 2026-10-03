"""Arquivo .tex <-> documento em blocos que o editor do site entende.

Cada bloco guarda o trecho original ("src") e o espaço antes dele ("pre"). Na volta, um bloco
que não foi editado é escrito exatamente como estava; só os blocos alterados são regerados.
"""
import re

from app.document.inline import parse_inline, strip_spans, to_latex
from app.document.texutils import find_env_end, match_brace, read_args, strip_tex

HEADINGS = {"part": 0, "chapter": 0, "section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}
ABSTRACTS = {"abstract", "abstract*", "resumo", "IEEEkeywords"}
LISTS = {"itemize", "enumerate", "description"}
FIGURES = {"figure", "figure*", "wrapfigure"}
TABLES = {"table", "table*"}
TABULARS = {"tabular", "tabular*", "tabularx", "longtable"}
HIDDEN = {
    "maketitle", "bibliographystyle", "label", "newpage", "clearpage", "tableofcontents", "vspace",
    "sloppy", "centering", "appendix", "pagebreak", "onecolumn", "twocolumn", "noindent", "medskip",
    "bigskip", "smallskip", "listoffigures", "listoftables",
}
BIBLIOGRAPHY = {"bibliography", "printbibliography"}
META_FIELDS = ("title", "author", "address")
COMMENT_LINE = re.compile(r"^[ \t]*%.*$", re.M)


def find_main(paths: list[str], read) -> str | None:
    candidates = [p for p in paths if p.lower().endswith(".tex")]
    with_class = [p for p in candidates if re.search(r"^[^%\n]*\\documentclass", read(p), re.M)]
    for group in (with_class, candidates):
        if group:
            return next((p for p in group if p.rsplit("/", 1)[-1] == "main.tex"), sorted(group, key=len)[0])
    return None


def uncommented(pattern: str, text: str, start: int = 0):
    for match in re.compile(pattern, re.M).finditer(text, start):
        line_start = text.rfind("\n", 0, match.start()) + 1
        if not re.search(r"(?<!\\)%", text[line_start:match.start()]):
            return match
    return None


# ---------- documento inteiro ----------

def parse_document(source: str) -> dict:
    begin = uncommented(r"\\begin\{document\}", source)
    if not begin:
        return {"preamble": "", "meta": {}, "blocks": parse_body(source), "tail": "", "fragment": True}

    ends = [m for m in re.finditer(r"\\end\{document\}", source) if m.start() > begin.end()]
    end = ends[-1].start() if ends else len(source)
    preamble = source[:begin.end()]
    body = source[begin.end():end]
    trailing = len(body) - len(body.rstrip())

    return {
        "preamble": preamble,
        "meta": parse_meta(preamble),
        "language": "en" if "sbc-template" in preamble else "pt" if re.search(r"brazil|portuguese|portugues", preamble) else "en",
        "blocks": parse_body(body[:len(body) - trailing]),
        "end_ws": body[len(body) - trailing:],
        "tail": source[end:],
    }


def parse_meta(preamble: str) -> dict:
    meta = {}
    for name in META_FIELDS:
        match = uncommented(r"\\" + name + r"\s*(\[[^\]]*\])?\s*\{", preamble)
        if not match:
            continue
        end = match_brace(preamble, match.end() - 1)
        if end == -1:
            continue
        content = preamble[match.end(): end - 1]
        meta[name] = {"spans": strip_spans(parse_inline(content)), "src": content, "start": match.end(), "end": end - 1}
    return meta


def serialize_document(doc: dict) -> str:
    preamble = doc.get("preamble", "")
    fields = sorted(doc.get("meta", {}).values(), key=lambda f: f["start"], reverse=True)
    for field in fields:
        original = field.get("src", "")
        new = original if to_latex(field["spans"]) == to_latex(strip_spans(parse_inline(original))) else to_latex(field["spans"])
        preamble = preamble[:field["start"]] + new + preamble[field["end"]:]

    body = "".join(block.get("pre", "\n\n") + serialize_block(block) for block in doc.get("blocks", []))
    if doc.get("fragment"):
        return body.lstrip("\n") + doc.get("end_ws", "\n")
    return preamble + body + doc.get("end_ws", "\n\n") + doc.get("tail", "\\end{document}\n")


# ---------- corpo: de texto para blocos ----------

def parse_body(body: str) -> list[dict]:
    blocks: list[dict] = []
    pos = 0
    last_end = 0
    para_start = para_end = None

    def add(block: dict, start: int, end: int):
        nonlocal last_end
        block["pre"] = body[last_end:start]
        blocks.append(block)
        last_end = end

    def flush():
        nonlocal para_start, para_end
        if para_start is not None:
            src = body[para_start:para_end]
            add({"type": "paragraph", "src": src, "spans": strip_spans(parse_inline(src))}, para_start, para_end)
        para_start = para_end = None

    while pos < len(body):
        line_end = body.find("\n", pos)
        line_end = len(body) if line_end == -1 else line_end
        line = body[pos:line_end]
        stripped = line.strip()
        start = pos + len(line) - len(line.lstrip())

        if not stripped:
            flush()
            pos = line_end + 1
            continue

        if stripped.startswith("%"):
            flush()
            end = line_end
            while True:
                nxt = body.find("\n", end + 1)
                nxt = len(body) if nxt == -1 else nxt
                if end + 1 < len(body) and body[end + 1:nxt].strip().startswith("%"):
                    end = nxt
                else:
                    break
            add({"type": "hidden", "kind": "comment", "src": body[start:end]}, start, end)
            pos = end + 1
            continue

        env_match = re.compile(r"\\begin\{([^}]+)\}").match(body, start)
        if env_match:
            found = find_env_end(body, env_match.end(), env_match.group(1))
            flush()
            if found:
                end = found[1]
                add(env_block(env_match.group(1), body[start:end]), start, end)
                pos = end
            else:
                add({"type": "raw", "src": body[start:line_end]}, start, line_end)
                pos = line_end + 1
            continue

        if stripped.startswith("\\end{"):
            flush()
            add({"type": "raw", "src": body[start:line_end]}, start, line_end)
            pos = line_end + 1
            continue

        command = re.compile(r"\\([a-zA-Z]+)(\*?)").match(body, start)
        name = command.group(1) if command else ""

        if name in HEADINGS:
            flush()
            args, end = read_args(body, command.end())
            title = next((c for k, c in reversed(args) if k == "{"), "")
            add({
                "type": "heading", "cmd": name, "star": bool(command.group(2)), "level": HEADINGS[name],
                "src": body[start:end], "spans": strip_spans(parse_inline(title)),
            }, start, end)
            pos = end
            continue

        if name in BIBLIOGRAPHY or name in HIDDEN:
            args, end = read_args(body, command.end())
            rest = body[end:line_end]
            if not rest.strip() or rest.strip().startswith("%") or name in ("label", "maketitle"):
                flush()
                if name in BIBLIOGRAPHY:
                    files = [f.strip() for k, c in args if k == "{" for f in c.split(",")]
                    add({"type": "references", "src": body[start:end], "files": files}, start, end)
                else:
                    key = args[-1][1].strip() if name == "label" and args else None
                    add({"type": "hidden", "kind": name, "src": body[start:end], "key": key}, start, end)
                pos = end
                continue

        if para_start is None:
            para_start = start
        para_end = line_end
        pos = line_end + 1

    flush()
    return blocks


def env_block(env: str, src: str) -> dict:
    inner_start = re.compile(r"\\begin\{[^}]+\}").match(src).end()
    _, inner_start = read_args(src, inner_start) if env in LISTS | TABULARS else (None, inner_start)
    inner = src[inner_start: src.rfind("\\end{")]

    if env in ABSTRACTS:
        paragraphs = [strip_spans(parse_inline(p)) for p in re.split(r"\n[ \t]*\n", inner) if p.strip()]
        return {"type": "abstract", "env": env, "src": src, "paragraphs": paragraphs}
    if env in LISTS:
        items = split_items(inner)
        if items is not None:
            return {"type": "list", "env": env, "src": src, "items": items}
    if env in FIGURES:
        return figure_block(src)
    if env in TABLES or env in TABULARS:
        return table_block(src)
    return {"type": "raw", "env": env, "src": src}


def split_items(inner: str) -> list[dict] | None:
    starts = []
    depth = 0
    pos = 0
    while pos < len(inner):
        char = inner[pos]
        if char == "\\":
            if inner.startswith("\\begin{", pos):
                depth += 1
            elif inner.startswith("\\end{", pos):
                depth -= 1
            elif depth == 0 and re.compile(r"\\item\b").match(inner, pos):
                starts.append(pos)
            pos += 2
            continue
        if char == "%":
            newline = inner.find("\n", pos)
            pos = len(inner) if newline == -1 else newline + 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        pos += 1

    if not starts or COMMENT_LINE.sub("", inner[:starts[0]]).strip():
        return None
    items = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(inner)
        body = inner[start + len("\\item"): end]
        option = None
        if body.startswith("["):
            close = match_brace(body, 0)
            option, body = body[:close], body[close:]
        items.append({"opt": option, "spans": strip_spans(parse_inline(body))})
    return items


# ---------- figuras e tabelas ----------

def top_level_ranges(src: str, env: str) -> list[tuple[int, int]]:
    ranges = []
    for match in re.finditer(r"\\begin\{" + re.escape(env) + r"\}", src):
        found = find_env_end(src, match.end(), env)
        if found:
            ranges.append((match.start(), found[1]))
    return ranges


def find_caption(src: str, skip: list[tuple[int, int]]) -> tuple[list, list] | tuple[None, None]:
    caption = None
    for match in re.finditer(r"\\caption\s*(\[[^\]]*\])?\s*\{", src):
        if any(a <= match.start() < b for a, b in skip) or is_commented(src, match.start()):
            continue
        end = match_brace(src, match.end() - 1)
        if end != -1:
            caption = (match.end(), end - 1)
    if not caption:
        return None, None
    return strip_spans(parse_inline(src[caption[0]:caption[1]])), list(caption)


def find_label(src: str, skip: list[tuple[int, int]]) -> str | None:
    labels = [m for m in re.finditer(r"\\label\{([^}]*)\}", src)
              if not any(a <= m.start() < b for a, b in skip) and not is_commented(src, m.start())]
    return labels[-1].group(1).strip() if labels else None


def is_commented(src: str, pos: int) -> bool:
    line_start = src.rfind("\n", 0, pos) + 1
    return bool(re.search(r"(?<!\\)%", src[line_start:pos]))


def graphics(src: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", src)
            if not is_commented(src, m.start())]


def figure_block(src: str) -> dict:
    subs = top_level_ranges(src, "subfigure")
    images = []
    for a, b in subs:
        part = src[a:b]
        cap, _ = find_caption(part, [])
        images += [{"path": path, "caption": cap} for path in graphics(part)]
    outside, last = "", 0
    for a, b in subs:
        outside += src[last:a]
        last = b
    outside += src[last:]
    images = [{"path": path, "caption": None} for path in graphics(outside)] + images
    caption, cap = find_caption(src, subs)
    return {"type": "figure", "src": src, "images": images, "caption": caption, "cap": cap, "label": find_label(src, subs)}


def table_block(src: str) -> dict:
    caption, cap = find_caption(src, [])
    block = {"type": "table", "src": src, "caption": caption, "cap": cap, "label": find_label(src, []),
             "columns": [], "rows": [], "note": []}

    tab = re.search(r"\\begin\{(tabularx|tabular\*?|longtable)\}", src)
    if not tab:
        return block
    found = find_env_end(src, tab.end(), tab.group(1))
    if not found:
        return block
    args, body_start = read_args(src, tab.end())
    spec = next((c for k, c in reversed(args) if k == "{"), "")
    block["columns"] = column_spec(spec)

    body = COMMENT_LINE.sub("", src[body_start:found[0]])
    for row in split_top(body, "\\\\"):
        row = re.sub(r"\\(hline|toprule|midrule|bottomrule)\b|\\cline\{[^}]*\}", "", row).strip()
        if row.startswith("["):
            row = row[max(match_brace(row, 0), 1):].strip()
        if row:
            block["rows"].append([strip_spans(parse_inline(cell)) for cell in split_top(row, "&")])

    after = src[found[1]: src.rfind("\\end{")]
    after = re.sub(r"\\(vspace|hspace)\*?\{[^}]*\}|\\(centering|small|footnotesize|scriptsize)\b|\\label\{[^}]*\}", "", after)
    if strip_tex(after):
        block["note"] = strip_spans(parse_inline(after.strip()))
    return block


def column_spec(spec: str) -> list[dict]:
    columns = []
    pos = 0
    while pos < len(spec):
        char = spec[pos]
        if char in "lcr":
            columns.append({"align": {"l": "left", "c": "center", "r": "right"}[char]})
        elif char == "X":
            columns.append({"align": "left", "grow": True})
        elif char in "pmb" and pos + 1 < len(spec) and spec[pos + 1] == "{":
            end = match_brace(spec, pos + 1)
            width = re.match(r"\s*([\d.]+)\s*(cm|mm|in|pt)", spec[pos + 2: end - 1])
            factor = {"cm": 1, "mm": 0.1, "in": 2.54, "pt": 0.0353}
            columns.append({"align": "left", "width_cm": float(width.group(1)) * factor[width.group(2)] if width else None})
            pos = end
            continue
        elif char in "@>{<" and pos + 1 < len(spec):
            nxt = spec.find("{", pos)
            if nxt != -1:
                pos = match_brace(spec, nxt)
                continue
        pos += 1
    return columns


def split_top(text: str, sep: str) -> list[str]:
    parts, depth, start, pos = [], 0, 0, 0
    while pos < len(text):
        if text.startswith(sep, pos) and depth == 0 and (sep != "&" or text[pos - 1:pos] != "\\"):
            parts.append(text[start:pos])
            pos += len(sep)
            start = pos
            continue
        char = text[pos]
        if char == "\\" and not text.startswith(sep, pos):
            pos += 2
            continue
        depth += {"{": 1, "}": -1}.get(char, 0)
        pos += 1
    parts.append(text[start:])
    return parts


# ---------- blocos: de volta para LaTeX ----------

def generate(block: dict) -> str:
    kind = block["type"]
    if kind == "paragraph":
        return to_latex(block["spans"])
    if kind == "heading":
        return f"\\{block.get('cmd', 'section')}{'*' if block.get('star') else ''}{{{to_latex(block['spans'])}}}"
    if kind == "list":
        env = block.get("env", "itemize")
        items = "\n".join(f"  \\item{item.get('opt') or ''} {to_latex(item['spans'])}" for item in block["items"])
        return f"\\begin{{{env}}}\n{items}\n\\end{{{env}}}"
    if kind == "abstract":
        env = block.get("env", "abstract")
        return f"\\begin{{{env}}}\n" + "\n\n".join(to_latex(p) for p in block["paragraphs"]) + f"\n\\end{{{env}}}"
    if kind in ("figure", "table") and block.get("cap") and block.get("caption") is not None:
        start, end = block["cap"]
        return block["src"][:start] + to_latex(block["caption"]) + block["src"][end:]
    return block.get("src", "")


def serialize_block(block: dict) -> str:
    generated = generate(block)
    src = block.get("src")
    if src is None or block["type"] in ("raw", "hidden", "references"):
        return generated
    reparsed = parse_body(src)
    if len(reparsed) == 1 and reparsed[0]["type"] == block["type"] and generate(reparsed[0]) == generated:
        return src
    return generated
