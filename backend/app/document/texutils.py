import re

ACCENTS = {
    "'": {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú", "A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú", "\\i": "í"},
    "`": {"a": "à", "e": "è", "o": "ò", "A": "À", "E": "È", "O": "Ò"},
    "^": {"a": "â", "e": "ê", "o": "ô", "A": "Â", "E": "Ê", "O": "Ô", "i": "î", "\\i": "î"},
    "~": {"a": "ã", "o": "õ", "n": "ñ", "A": "Ã", "O": "Õ", "N": "Ñ"},
    '"': {"a": "ä", "e": "ë", "i": "ï", "o": "ö", "u": "ü", "A": "Ä", "O": "Ö", "U": "Ü"},
    "c": {"c": "ç", "C": "Ç"},
}
ACCENT_RE = re.compile(r"""\\(['`^~"]|c(?=[\s{]))\s*(?:\{(\\i|[A-Za-z])\}|(\\i|[A-Za-z]))""")
LIGATURES = [("---", "—"), ("--", "–"), ("``", "“"), ("''", "”")]
ESCAPED = {"%", "&", "_", "#", "$", "{", "}"}


def match_brace(text: str, start: int) -> int:
    """text[start] é '{' (ou '['); devolve o índice logo depois do fechamento correspondente."""
    opening = text[start]
    closing = "}" if opening == "{" else "]"
    depth = 0
    pos = start
    while pos < len(text):
        char = text[pos]
        if char == "\\":
            pos += 2
            continue
        if char == "%":
            newline = text.find("\n", pos)
            pos = len(text) if newline == -1 else newline + 1
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    return -1


def read_args(text: str, pos: int, max_args: int = 9) -> tuple[list[tuple[str, str]], int]:
    """Lê argumentos [opcionais] e {obrigatórios} a partir de pos. Devolve [(tipo, conteúdo)] e a posição final."""
    args = []
    while len(args) < max_args:
        probe = pos
        while probe < len(text) and text[probe] in " \t":
            probe += 1
        if probe < len(text) and text[probe] == "\n" and probe + 1 < len(text) and text[probe + 1] in "{[":
            probe += 1
        if probe >= len(text) or text[probe] not in "{[":
            break
        end = match_brace(text, probe)
        if end == -1:
            break
        args.append((text[probe], text[probe + 1: end - 1]))
        pos = end
    return args, pos


def find_env_end(text: str, pos: int, name: str) -> tuple[int, int] | None:
    """Procura o \\end{name} que fecha o ambiente aberto antes de pos. Devolve (início do \\end, fim)."""
    pattern = re.compile(r"(?<!\\)(%.*$)|\\(begin|end)\{" + re.escape(name) + r"\}", re.M)
    depth = 1
    for match in pattern.finditer(text, pos):
        if match.group(1):
            continue
        depth += 1 if match.group(2) == "begin" else -1
        if depth == 0:
            return match.start(), match.end()
    return None


def convert_accents(text: str) -> str:
    def replace(match):
        mark = match.group(1).strip()
        letter = match.group(2) or match.group(3)
        return ACCENTS.get(mark, {}).get(letter, match.group(0))
    return ACCENT_RE.sub(replace, text)


def normalize(text: str) -> str:
    """Equivalências tipográficas do LaTeX, para o diff não acusar ``aspas'' trocadas por “aspas”."""
    text = convert_accents(text)
    for tex, char in LIGATURES:
        text = text.replace(tex, char)
    return text


def escape(text: str) -> str:
    out = []
    for char in text:
        if char == "\\":
            out.append(r"\textbackslash{}")
        elif char in ESCAPED:
            out.append("\\" + char)
        elif char == "~":
            out.append(r"\textasciitilde{}")
        elif char == "^":
            out.append(r"\textasciicircum{}")
        elif char == "\u00a0":
            out.append("~")
        else:
            out.append(char)
    return "".join(out)


def strip_tex(text: str) -> str:
    """Texto legível de um trecho LaTeX simples (campos do .bib, legendas em tabelas etc.)."""
    text = normalize(text)
    text = re.sub(r"(?<!\\)%.*", "", text)
    text = re.sub(r"\\(url|href)\{([^{}]*)\}(\{[^{}]*\})?", r"\2", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?", "", text)
    text = text.replace("~", " ")
    text = re.sub(r"\\([%&_#$])", r"\1", text)
    text = text.replace("{", "").replace("}", "")
    return " ".join(text.split())
