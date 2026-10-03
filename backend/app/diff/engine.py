from difflib import unified_diff
from pathlib import PurePosixPath
from collections.abc import Callable

from app.diff.bib import diff_bib
from app.diff.latex import diff_tex
from app.ingest import decode_text
from app.models import Blob


def diff_lines(old_text: str, new_text: str) -> dict:
    lines = list(unified_diff(old_text.splitlines(), new_text.splitlines(), lineterm="", n=3))
    body = lines[2:]
    return {
        "kind": "lines",
        "stats": {
            "added": sum(1 for l in body if l.startswith("+")),
            "removed": sum(1 for l in body if l.startswith("-")),
        },
        "patch": "\n".join(body),
    }


def diff_content(path: str, old: Blob, new: Blob) -> dict | None:
    if not (old.is_text and new.is_text):
        return None
    old_text, new_text = decode_text(old.content), decode_text(new.content)
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".tex":
        return diff_tex(old_text, new_text)
    if suffix == ".bib":
        return diff_bib(old_text, new_text)
    return diff_lines(old_text, new_text)


def diff_trees(old: dict[str, str], new: dict[str, str], load: Callable[[str], Blob]) -> list[dict]:
    """old/new: caminho -> hash do blob. Só carrega o conteúdo dos arquivos alterados."""
    removed = {path: h for path, h in old.items() if path not in new}
    added = {path: h for path, h in new.items() if path not in old}

    files = []
    for path in sorted(removed):
        # Mesmo conteúdo em outro caminho: é renomeação, não remoção + adição.
        renamed_to = next((p for p, h in sorted(added.items()) if h == removed[path]), None)
        if renamed_to:
            files.append({"path": renamed_to, "old_path": path, "status": "renamed"})
            del added[renamed_to]
        else:
            files.append({"path": path, "status": "removed"})

    files += [{"path": path, "status": "added"} for path in sorted(added)]

    for path in sorted(old.keys() & new.keys()):
        if old[path] != new[path]:
            files.append({"path": path, "status": "modified", "diff": diff_content(path, load(old[path]), load(new[path]))})

    return sorted(files, key=lambda f: f["path"])
