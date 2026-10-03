import re

ENTRY_START = re.compile(r"@(\w+)\s*[{(]", re.IGNORECASE)
SKIP_TYPES = {"comment", "string", "preamble"}


def matching_close(text: str, open_pos: int) -> int:
    depth = 0
    for pos in range(open_pos, len(text)):
        if text[pos] in "{(":
            depth += 1
        elif text[pos] in "})":
            depth -= 1
            if depth == 0:
                return pos
    return len(text)


def parse_fields(body: str) -> dict[str, str]:
    fields = {}
    pos = 0
    while True:
        match = re.compile(r"\s*,?\s*([\w:-]+)\s*=\s*").match(body, pos)
        if not match:
            break
        name, pos = match.group(1).lower(), match.end()
        if pos < len(body) and body[pos] == "{":
            end = matching_close(body, pos)
            value, pos = body[pos + 1: end], end + 1
        elif pos < len(body) and body[pos] == '"':
            end = body.find('"', pos + 1)
            end = len(body) if end == -1 else end
            value, pos = body[pos + 1: end], end + 1
        else:
            value_match = re.compile(r"[^,]*").match(body, pos)
            value, pos = value_match.group(0), value_match.end()
        fields[name] = " ".join(value.split())
    return fields


def parse_bib(text: str) -> dict[str, dict]:
    entries = {}
    for match in ENTRY_START.finditer(text):
        entry_type = match.group(1).lower()
        if entry_type in SKIP_TYPES:
            continue
        close = matching_close(text, match.end() - 1)
        inner = text[match.end(): close]
        key, _, body = inner.partition(",")
        entries[key.strip()] = {"type": entry_type, "fields": parse_fields(body)}
    return entries


def diff_bib(old_text: str, new_text: str) -> dict:
    old, new = parse_bib(old_text), parse_bib(new_text)
    changes = []
    for key in sorted(old.keys() - new.keys()):
        changes.append({"op": "delete", "key": key, "old": old[key]})
    for key in sorted(new.keys() - old.keys()):
        changes.append({"op": "insert", "key": key, "new": new[key]})
    for key in sorted(old.keys() & new.keys()):
        a, b = old[key], new[key]
        if a == b:
            continue
        fields = {
            name: {"old": a["fields"].get(name), "new": b["fields"].get(name)}
            for name in sorted(a["fields"].keys() | b["fields"].keys())
            if a["fields"].get(name) != b["fields"].get(name)
        }
        if a["type"] != b["type"]:
            fields["@type"] = {"old": a["type"], "new": b["type"]}
        changes.append({"op": "modify", "key": key, "fields": fields})

    count = lambda op: sum(1 for c in changes if c["op"] == op)
    return {
        "kind": "bib",
        "stats": {
            "entries_before": len(old), "entries_after": len(new),
            "added": count("insert"), "removed": count("delete"), "modified": count("modify"),
        },
        "changes": changes,
    }
