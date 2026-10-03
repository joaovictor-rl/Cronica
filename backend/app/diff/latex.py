import re
from difflib import SequenceMatcher

from app.document.texutils import normalize

ABBREVIATIONS = {
    "et al.", "al.", "e.g.", "i.e.", "fig.", "figs.", "eq.", "eqs.", "sec.", "ref.", "cf.", "vs.",
    "dr.", "prof.", "p.", "pp.", "vol.", "no.", "ex.", "etc.", "approx.", "tab.", "cap.", "art.",
}
STRUCTURAL = re.compile(
    r"(\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter|caption|label)\*?"
    r"(?:\[[^\]]*\]|\{(?:[^{}]|\{[^{}]*\})*\})*"
    r"|\\item\b(?:\[[^\]]*\])?)"
)
BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý\\`\"'(\[])")
TOKEN = re.compile(
    r"\\[a-zA-Z@]+\*?(?:\s*\[[^\]]*\])*(?:\s*\{(?:[^{}]|\{[^{}]*\})*\})*"  # comando e argumentos
    r"|\$\$.+?\$\$|\$[^$]+\$"                                            # matemática
    r"|\\."                                                             # \%, \&, \\ ...
    r"|[\wÀ-ÿ]+(?:['’-][\wÀ-ÿ]+)*"                                      # palavra
    r"|\S"
)


def strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        match = re.search(r"(?<!\\)%", line)
        lines.append(line[: match.start()] if match else line)
    return "\n".join(lines)


def split_sentences(paragraph: str) -> list[str]:
    sentences = []
    start = 0
    for match in BOUNDARY.finditer(paragraph):
        before = paragraph[start: match.start()]
        last_word = before.rsplit(None, 1)[-1].lower() if before.split() else ""
        last_two = " ".join(before.lower().split()[-2:])
        if last_word in ABBREVIATIONS or last_two in ABBREVIATIONS or re.fullmatch(r"[a-z]\.", last_word):
            continue
        sentences.append(before)
        start = match.end()
    sentences.append(paragraph[start:])
    return sentences


def units(text: str) -> list[str]:
    """Quebra o .tex em unidades comparáveis: frases e comandos estruturais."""
    result = []
    for paragraph in re.split(r"\n\s*\n", normalize(strip_comments(text))):
        flat = " ".join(paragraph.split())
        for piece in STRUCTURAL.split(flat):
            for sentence in split_sentences(piece.strip()):
                if sentence.strip():
                    result.append(sentence.strip())
    return result


def tokens(sentence: str) -> list[str]:
    return TOKEN.findall(sentence)


def is_markup(token: str) -> bool:
    return token.startswith("\\") or token.startswith("$")


def word_diff(old: str, new: str) -> tuple[list[dict], bool]:
    a_spans = [m.span() for m in TOKEN.finditer(old)]
    b_spans = [m.span() for m in TOKEN.finditer(new)]
    a = [old[s:e] for s, e in a_spans]
    b = [new[s:e] for s, e in b_spans]

    # Cada trecho leva o espaço que vem antes dele; assim os textos antigo e novo
    # podem ser remontados exatamente, sem juntar tudo com espaço.
    def chunk(text, spans, i1, i2):
        start = spans[i1 - 1][1] if i1 > 0 else 0
        end = spans[i2 - 1][1] if i2 < len(spans) else len(text)
        return text[start:end]

    ops = []
    changed = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"op": "equal", "text": chunk(old, a_spans, i1, i2)})
            continue
        if i2 > i1:
            ops.append({"op": "delete", "text": chunk(old, a_spans, i1, i2)})
        if j2 > j1:
            inserted = chunk(new, b_spans, j1, j2)
            if i1 == i2 == 0 and j2 < len(b_spans):
                # Inserção no começo da frase: o espaço que a separa do resto vem junto.
                inserted += new[b_spans[j2 - 1][1]:b_spans[j2][0]]
            ops.append({"op": "insert", "text": inserted})
        changed += a[i1:i2] + b[j1:j2]
    only_markup = bool(changed) and all(is_markup(t) for t in changed)
    return ops, only_markup


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, tokens(a), tokens(b), autojunk=False).ratio()


def pair_block(old: list[str], new: list[str], i0: int, j0: int) -> list[dict]:
    # Dentro de um trecho alterado, casa cada frase antiga com a nova mais parecida, mantendo a ordem.
    changes = []
    j = 0
    for i, sentence in enumerate(old):
        match = next((k for k in range(j, len(new)) if similarity(sentence, new[k]) >= 0.5), None)
        if match is None:
            changes.append({"op": "delete", "old_index": i0 + i, "old": sentence})
            continue
        for k in range(j, match):
            changes.append({"op": "insert", "new_index": j0 + k, "new": new[k]})
        words, only_markup = word_diff(sentence, new[match])
        changes.append({
            "op": "modify", "old_index": i0 + i, "new_index": j0 + match,
            "old": sentence, "new": new[match], "words": words, "only_markup": only_markup,
        })
        j = match + 1
    for k in range(j, len(new)):
        changes.append({"op": "insert", "new_index": j0 + k, "new": new[k]})
    return changes


def diff_tex(old_text: str, new_text: str) -> dict:
    old, new = units(old_text), units(new_text)
    norm = lambda s: " ".join(tokens(s))
    matcher = SequenceMatcher(None, [norm(s) for s in old], [norm(s) for s in new], autojunk=False)

    changes = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            changes += pair_block(old[i1:i2], new[j1:j2], i1, j1)

    count = lambda op: sum(1 for c in changes if c["op"] == op)
    return {
        "kind": "tex",
        "stats": {
            "sentences_before": len(old), "sentences_after": len(new),
            "added": count("insert"), "removed": count("delete"), "modified": count("modify"),
        },
        "changes": changes,
    }
