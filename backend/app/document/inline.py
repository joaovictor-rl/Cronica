"""Texto corrido em LaTeX <-> lista de trechos ("spans") que o editor do site consegue mostrar.

Um trecho pode ser:
  {"t": "texto", "b": True, "i": "emph"}    texto, com negrito/itálico opcionais
  {"raw": "\\cite{x}", "kind": "cite", ...}  comando LaTeX preservado como está
  {"br": True}                               quebra de linha (\\\\)
"""
import re

from app.document.texutils import (
    ACCENT_RE,
    ACCENTS,
    ESCAPED,
    escape,
    find_env_end,
    match_brace,
    read_args,
)

FORMAT = {"textbf": "b", "textit": "i", "emph": "i"}
CITE = {"cite", "citep", "citet", "citeonline", "citeauthor", "citeyear", "apud", "nocite"}
REF = {"ref", "eqref", "autoref", "pageref", "cref", "Cref"}
SYMBOLS = {
    "ldots": "…", "dots": "…", "textendash": "–", "textemdash": "—", "LaTeX": "LaTeX", "TeX": "TeX",
    "textquotedblleft": "“", "textquotedblright": "”", "textbackslash": "\\", "textasciitilde": "~",
    "textasciicircum": "^", "S": "§", "%": "%",
}
LIGATURES = [("---", "—"), ("--", "–"), ("``", "“"), ("''", "”")]
INVISIBLE = {
    "vspace", "hspace", "hfill", "vfill", "index", "phantom", "setlength", "renewcommand", "newcommand",
    "setcounter", "addtocounter", "centering", "small", "footnotesize", "scriptsize", "large", "Large",
    "normalsize", "noindent", "par", "linebreak", "pagebreak", "newpage", "clearpage", "sloppy",
}
NO_TEXT_ARGS = {"vspace", "hspace", "index", "phantom", "setlength", "renewcommand", "newcommand", "setcounter", "addtocounter"}
CONTROL_WORD_END = re.compile(r"\\[a-zA-Z@]+\*?$")


def parse_inline(text: str, fmt: dict | None = None) -> list[dict]:
    fmt = fmt or {}
    spans: list[dict] = []
    buf: list[str] = []
    pos = 0

    def flush():
        if buf:
            spans.append({"t": "".join(buf), **fmt})
            buf.clear()

    def raw(latex, kind, label="", **extra):
        flush()
        spans.append({"raw": latex, "kind": kind, "label": label, **fmt, **extra})

    while pos < len(text):
        char = text[pos]

        if char == "\\":
            if text.startswith("\\\\", pos):
                flush()
                spans.append({"br": True})
                pos += 2
                if pos < len(text) and text[pos] == "[":
                    pos = max(match_brace(text, pos), pos + 1)
                continue

            accent = ACCENT_RE.match(text, pos)
            if accent:
                mark = accent.group(1).strip()
                buf.append(ACCENTS[mark].get(accent.group(2) or accent.group(3), accent.group(0)))
                pos = accent.end()
                continue

            word = re.compile(r"\\([a-zA-Z@]+)(\*?)").match(text, pos)
            if not word:
                symbol = text[pos + 1: pos + 2]
                if symbol in ESCAPED:
                    buf.append(symbol)
                    pos += 2
                elif symbol in "([":
                    closing = "\\)" if symbol == "(" else "\\]"
                    end = text.find(closing, pos + 2)
                    end = len(text) if end == -1 else end + 2
                    raw(text[pos:end], "math", text[pos + 2: end - 2].strip())
                    pos = end
                else:
                    raw(text[pos: pos + 2], "cmd", " " if symbol in " ,;:\n" else "")
                    pos += 2
                continue

            name = word.group(1)
            after = word.end()

            if name in FORMAT and after < len(text) and text[after] == "{":
                end = match_brace(text, after)
                if end != -1:
                    flush()
                    inner_fmt = {**fmt, "b": True} if FORMAT[name] == "b" else {**fmt, "i": name}
                    spans.extend(parse_inline(text[after + 1: end - 1], inner_fmt))
                    pos = end
                    continue

            if name in SYMBOLS:
                buf.append(SYMBOLS[name])
                pos = after + 2 if text.startswith("{}", after) else after
                continue

            if name == "begin":
                args, end = read_args(text, after, 1)
                env = args[0][1] if args else ""
                found = find_env_end(text, end, env) if env else None
                end = found[1] if found else end
                raw(text[pos:end], "env", env)
                pos = end
                continue

            args, end = read_args(text, after)
            mandatory = [content for kind, content in args if kind == "{"]
            if not args and end < len(text) and text[end] == " ":
                end += 1  # o espaço depois de \comando é engolido pelo LaTeX; fica junto do comando
            latex = text[pos:end]
            last = mandatory[-1] if mandatory else ""

            if name in CITE:
                raw(latex, "cite", "", keys=[k.strip() for k in last.split(",") if k.strip()])
            elif name in REF:
                raw(latex, "ref", "??", key=last.strip())
            elif name == "footnote":
                raw(latex, "footnote", "", text=plain_text(parse_inline(last)))
            elif name == "url":
                raw(latex, "url", last, href=last)
            elif name == "href" and len(mandatory) >= 2:
                raw(latex, "url", plain_text(parse_inline(mandatory[1])), href=mandatory[0])
            elif name == "label":
                raw(latex, "label", "", key=last.strip())
            elif name in ("textsuperscript", "inst"):
                raw(latex, "sup", plain_text(parse_inline(last)))
            elif name in INVISIBLE and (not mandatory or name in NO_TEXT_ARGS):
                raw(latex, "cmd", "")
            else:
                raw(latex, "cmd", plain_text(parse_inline(last)) if mandatory else "")
            pos = end
            continue

        if char == "$":
            double = text.startswith("$$", pos)
            delim = "$$" if double else "$"
            end = pos + len(delim)
            while True:
                end = text.find(delim, end)
                if end == -1 or text[end - 1] != "\\":
                    break
                end += 1
            end = len(text) if end == -1 else end + len(delim)
            raw(text[pos:end], "math", text[pos + len(delim): end - len(delim)].strip())
            pos = end
            continue

        if char == "%":
            end = text.find("\n", pos)
            end = len(text) if end == -1 else end + 1
            raw(text[pos:end], "comment", "", text=text[pos + 1:end].strip())
            pos = end
            continue

        if char == "{":
            end = match_brace(text, pos)
            if end == -1:
                buf.append("{")
                pos += 1
            else:
                raw(text[pos:end], "group", plain_text(parse_inline(text[pos + 1: end - 1])))
                pos = end
            continue

        if char == "~":
            buf.append("\u00a0")
            pos += 1
            continue

        ligature = next((uni for tex, uni in LIGATURES if text.startswith(tex, pos)), None)
        if ligature:
            buf.append(ligature)
            pos += len(next(tex for tex, uni in LIGATURES if uni == ligature))
            continue

        buf.append(char)
        pos += 1

    flush()
    return tidy(spans)


def tidy(spans: list[dict]) -> list[dict]:
    """Junta trechos de texto vizinhos com o mesmo formato e reduz espaços repetidos."""
    out: list[dict] = []
    for span in spans:
        if "t" in span:
            span = {**span, "t": re.sub(r"[ \t\r\n]+", " ", span["t"])}
            if out and "t" in out[-1] and same_format(out[-1], span):
                out[-1] = {**out[-1], "t": out[-1]["t"] + span["t"]}
                continue
            if not span["t"]:
                continue
        out.append(span)
    return out


def same_format(a: dict, b: dict) -> bool:
    return bool(a.get("b")) == bool(b.get("b")) and a.get("i") == b.get("i")


def strip_spans(spans: list[dict]) -> list[dict]:
    spans = [dict(s) for s in spans]
    while spans and "t" in spans[0] and not spans[0]["t"].strip():
        spans.pop(0)
    while spans and "t" in spans[-1] and not spans[-1]["t"].strip():
        spans.pop()
    if spans and "t" in spans[0]:
        spans[0]["t"] = spans[0]["t"].lstrip()
    if spans and "t" in spans[-1]:
        spans[-1]["t"] = spans[-1]["t"].rstrip()
    return spans


def to_latex(spans: list[dict]) -> str:
    out = ""
    group: list[dict] = []

    def emit(piece: str):
        nonlocal out
        if piece and CONTROL_WORD_END.search(out) and piece[0].isalpha():
            out += " "
        out += piece

    def close_group():
        if not group:
            return
        inner = ""
        for span in group:
            piece = escape(span["t"]) if "t" in span else span.get("raw", "")
            if piece and CONTROL_WORD_END.search(inner) and piece[0].isalpha():
                inner += " "
            inner += piece
        first = group[0]
        if first.get("i"):
            inner = f"\\{first['i']}{{{inner}}}"
        if first.get("b"):
            inner = f"\\textbf{{{inner}}}"
        emit(inner)
        group.clear()

    for span in spans:
        if span.get("br"):
            close_group()
            emit("\\\\\n")
            continue
        if group and not same_format(group[0], span):
            close_group()
        group.append(span)
    close_group()
    return out


def plain_text(spans: list[dict]) -> str:
    parts = []
    for span in spans:
        if "t" in span:
            parts.append(span["t"])
        elif span.get("br"):
            parts.append("\n")
        elif span.get("kind") not in ("comment", "label"):
            parts.append(span.get("label", ""))
    return re.sub(r"[ \t]+", " ", "".join(parts)).replace("\u00a0", " ").strip()
