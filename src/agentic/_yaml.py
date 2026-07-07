"""YAML load/dump.

Uses PyYAML when available; otherwise falls back to a small block-style parser
that handles the subset Agentic bundles use (block maps, block lists, scalar
inline lists/maps, comments, quoted strings, and bool/int/float/null scalars).
The dumper always emits the same block subset so the fallback can round-trip
anything this CLI writes, with zero third-party dependencies.
"""
from __future__ import annotations

try:  # prefer the real thing if the user has it
    import yaml as _pyyaml
except Exception:  # pragma: no cover - exercised on stock installs
    _pyyaml = None


# ---------------------------------------------------------------- scalars
def _parse_scalar(tok: str):
    tok = tok.strip()
    if tok == "" or tok == "~" or tok == "null":
        return None
    if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
        return tok[1:-1]
    low = tok.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


def _split_top(s: str):
    """Split a flow body on commas that are not inside quotes/brackets."""
    parts, depth, buf, quote = [], 0, [], None
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return parts


def _parse_flow(tok: str):
    tok = tok.strip()
    if tok.startswith("[") and tok.endswith("]"):
        inner = tok[1:-1].strip()
        return [_parse_flow(p.strip()) for p in _split_top(inner)] if inner else []
    if tok.startswith("{") and tok.endswith("}"):
        inner = tok[1:-1].strip()
        out = {}
        for p in _split_top(inner):
            if ":" in p:
                k, v = p.split(":", 1)
                out[k.strip()] = _parse_flow(v.strip())
        return out
    return _parse_scalar(tok)


# ---------------------------------------------------------------- lines
def _strip_comment(line: str) -> str:
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _prep(text: str):
    rows = []
    for raw in text.splitlines():
        line = _strip_comment(raw).rstrip()
        if line.strip() == "":
            continue
        indent = len(line) - len(line.lstrip(" "))
        rows.append((indent, line.strip()))
    return rows


def _parse_block(rows, idx, indent):
    """Return (value, next_idx) for the block at column >= indent."""
    if idx >= len(rows):
        return None, idx
    first_indent, first = rows[idx]
    is_seq = first.startswith("- ") or first == "-"

    if is_seq:
        seq = []
        while idx < len(rows):
            cur_indent, cur = rows[idx]
            if cur_indent < indent or not (cur.startswith("- ") or cur == "-"):
                break
            rest = cur[1:].strip()
            if rest == "":
                idx += 1
                val, idx = _parse_block(rows, idx, cur_indent + 1)
                seq.append(val)
            elif ":" in rest and not rest.startswith("[") and not rest.startswith("{"):
                # inline map item: first key sits at cur_indent + 2 (after "- "),
                # its sibling keys share that column, its nested value is deeper.
                key_col = cur_indent + 2
                item = {}
                k, v = rest.split(":", 1)
                k, v = k.strip(), v.strip()
                idx += 1
                if v == "":
                    if idx < len(rows) and rows[idx][0] > key_col:
                        child, idx = _parse_block(rows, idx, rows[idx][0])
                        item[k] = child
                    else:
                        item[k] = None
                else:
                    item[k] = _parse_flow(v)
                # remaining sibling keys of THIS item, at exactly key_col
                while idx < len(rows) and rows[idx][0] == key_col and not (
                    rows[idx][1].startswith("- ") or rows[idx][1] == "-"
                ):
                    _, idx = _parse_kv(rows, idx, key_col, item)
                seq.append(item)
            else:
                seq.append(_parse_flow(rest))
                idx += 1
        return seq, idx

    # mapping
    mapping = {}
    while idx < len(rows):
        cur_indent, cur = rows[idx]
        if cur_indent < indent:
            break
        if cur.startswith("- ") or cur == "-":
            break
        _, idx = _parse_kv(rows, idx, indent, mapping)
    return mapping, idx


def _parse_kv(rows, idx, indent, mapping):
    cur_indent, cur = rows[idx]
    key, _, val = cur.partition(":")
    key = key.strip()
    val = val.strip()
    idx += 1
    if val == "":
        # nested block (map or seq) if the next row is deeper / a seq at same col
        if idx < len(rows):
            nxt_indent, nxt = rows[idx]
            is_child = nxt_indent > cur_indent or (
                nxt_indent == cur_indent and (nxt.startswith("- ") or nxt == "-")
            )
            if is_child:
                child, idx = _parse_block(rows, idx, cur_indent + 1 if nxt_indent > cur_indent else cur_indent)
                mapping[key] = child
                return key, idx
        mapping[key] = None
    else:
        mapping[key] = _parse_flow(val)
    return key, idx


def _mini_load(text: str):
    rows = _prep(text)
    if not rows:
        return {}
    val, _ = _parse_block(rows, 0, rows[0][0])
    return val


# ---------------------------------------------------------------- dump
def _needs_quote(s: str) -> bool:
    if s == "":
        return True
    if not isinstance(_parse_scalar(s), str):
        return True  # would round-trip to a bool/int/float/null — keep it a string
    if s.strip() != s:
        return True
    if s[0] in "!&*?|>%@`\"'#-[]{},:":
        return True
    if s.lower() in ("true", "false", "yes", "no", "null", "~"):
        return True
    if ":" in s or "#" in s:
        return True
    return False


def _dump_scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    return '"' + s.replace('"', '\\"') + '"' if _needs_quote(s) else s


def _dump(obj, indent=0):
    pad = "  " * indent
    lines = []
    if isinstance(obj, dict):
        if not obj:
            return [pad + "{}"]
        for k, v in obj.items():
            if isinstance(v, dict) and v:
                lines.append(f"{pad}{k}:")
                lines += _dump(v, indent + 1)
            elif isinstance(v, list) and v:
                lines.append(f"{pad}{k}:")
                lines += _dump(v, indent + 1)
            elif isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}: " + ("{}" if isinstance(v, dict) else "[]"))
            else:
                lines.append(f"{pad}{k}: {_dump_scalar(v)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and item:
                sub = _dump(item, indent + 1)
                first = sub[0].lstrip()
                lines.append(f"{pad}- {first}")
                lines += sub[1:]
            elif isinstance(item, (dict, list)):
                lines.append(f"{pad}- " + ("{}" if isinstance(item, dict) else "[]"))
            else:
                lines.append(f"{pad}- {_dump_scalar(item)}")
    return lines


# ---------------------------------------------------------------- public
def load(text: str):
    if _pyyaml is not None:
        return _pyyaml.safe_load(text)
    return _mini_load(text)


def dump(obj) -> str:
    if _pyyaml is not None:
        return _pyyaml.safe_dump(obj, sort_keys=False, default_flow_style=False)
    return "\n".join(_dump(obj)) + "\n"


USING_PYYAML = _pyyaml is not None
