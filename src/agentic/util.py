"""Small self-contained helpers: ULID ids, hash-chain integrity, glob matching."""
from __future__ import annotations

import hashlib
import json
import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _b32(n: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_CROCKFORD[n & 0x1F])
        n >>= 5
    return "".join(reversed(out))


def ulid() -> str:
    """A ULID: 48-bit ms timestamp + 80 bits of randomness, Crockford base32."""
    ms = int(time.time() * 1000)
    rand = int.from_bytes(os.urandom(10), "big")
    return _b32(ms, 10) + _b32(rand, 16)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def chain_hash(prev_hash: str, entry: dict) -> str:
    """Tamper-evident hash chain (POC stand-in for ed25519 signing)."""
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256((prev_hash + canonical(body)).encode("utf-8")).hexdigest()


def glob_match(pattern: str, path: str) -> bool:
    """Match a path against a glob supporting ** (any depth) and * (one segment)."""
    path = path.replace("\\", "/").lstrip("./")
    pattern = pattern.replace("\\", "/").lstrip("./")
    re_parts = ["^"]
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 2] == "**":
                # consume '**' and an optional following '/'
                i += 2
                if pattern[i : i + 1] == "/":
                    i += 1
                re_parts.append(".*")
                continue
            re_parts.append("[^/]*")
        elif c == "?":
            re_parts.append("[^/]")
        elif c in ".^$+{}()[]|\\":
            re_parts.append("\\" + c)
        else:
            re_parts.append(c)
        i += 1
    re_parts.append("$")
    import re as _re

    return _re.match("".join(re_parts), path) is not None


def find_project_root(start: str | None = None) -> str | None:
    """Walk up from `start` (or cwd) looking for a `.agentic/` directory."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, ".agentic")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent
