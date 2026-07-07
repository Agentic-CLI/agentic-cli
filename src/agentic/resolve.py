"""Resolve ``extends:`` git sources into an effective bundle — the *pack* layer.

A client keeps reusable personas/packs in their own git repo; each project pins
them by ref, and this module fetches, caches, **sha-locks**, and merges them into
a concrete bundle that the projector and gate consume unchanged.

Source syntax (Terraform-style)::

    git::<repo-url>//<subpath>[@<ref>]
    git::https://github.com/acme/agentic//personas/security-reviewer.yaml@v1.2.0

``<repo-url>`` may be an https URL, an ``ssh``/``git`` URL, a ``file://`` URL, or a
local path (the last two make offline testing trivial). ``<ref>`` is any
commit / tag / branch; the resolved **commit sha** is written to the lockfile so
resolution is reproducible and the ledger can record exactly which pack version
governed a run.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

from . import _yaml, bundle

LOCK_REL = os.path.join(".agentic", "agentic.lock")


def _cache_dir() -> str:
    return os.environ.get("AGENTIC_CACHE") or os.path.join(
        os.path.expanduser("~"), ".agentic", "cache"
    )


def parse_source(entry: str):
    """``git::<repo>//<subpath>[@<ref>]`` → ``(repo, subpath, ref)``."""
    if not entry.startswith("git::"):
        raise ValueError(f"unsupported source (expected 'git::' prefix): {entry}")
    body = entry[len("git::") :]
    ref = None
    slash = body.rfind("/")
    at = body.rfind("@")
    if at > slash:  # an @ref after the last path separator (not an scp/user@host)
        body, ref = body[:at], body[at + 1 :]
    scheme = body.find("://")
    start = scheme + 3 if scheme != -1 else 0
    sep = body.find("//", start)
    if sep == -1:
        return body, "", ref
    return body[:sep], body[sep + 2 :], ref


def _git(args, cwd=None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo_cache(repo: str) -> str:
    key = hashlib.sha256(repo.encode()).hexdigest()[:16]
    return os.path.join(_cache_dir(), key)


def fetch(repo: str, ref: str | None):
    """Clone/refresh ``repo`` into the cache, checkout ``ref``; return
    ``(checkout_dir, resolved_commit_sha)``."""
    dest = _repo_cache(repo)
    if not os.path.isdir(os.path.join(dest, ".git")):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        _git(["clone", "--quiet", repo, dest])
    else:
        try:
            _git(["fetch", "--quiet", "--tags", "--force", "origin"], cwd=dest)
        except subprocess.CalledProcessError:
            pass  # offline: fall back to what's already cached
    if ref:
        _git(["checkout", "--quiet", ref], cwd=dest)
    return dest, _git(["rev-parse", "HEAD"], cwd=dest)


# ─────────────────────────────────────────────────────────── lockfile
def lock_path(root: str) -> str:
    return os.path.join(root, LOCK_REL)


def load_lock(root: str) -> dict:
    p = lock_path(root)
    if os.path.exists(p):
        try:
            return json.load(open(p))
        except Exception:
            pass
    return {"lock_version": "1", "sources": {}}


def save_lock(root: str, lock: dict) -> None:
    p = lock_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(lock, f, indent=2, sort_keys=True)
        f.write("\n")


# ─────────────────────────────────────────────────────────── merge
def _merge_role(defn: dict, local: dict) -> dict:
    """Base persona definition + this repo's local fields/overrides."""
    role = {k: v for k, v in defn.items() if k not in ("kind", "version")}
    role["id"] = defn.get("id") or local.get("use")
    for k, v in local.items():
        if k in ("use", "overrides"):
            continue
        role[k] = v
    for k, v in (local.get("overrides") or {}).items():
        if isinstance(v, list) and isinstance(role.get(k), list):
            role[k] = role[k] + [x for x in v if x not in role[k]]
        else:
            role[k] = v
    return role


def effective_bundle(root: str, update: bool = False) -> dict:
    """Load the bundle, resolve every ``extends:`` source (pinned via the
    lockfile unless ``update``), materialize ``use:`` roles, and return the
    concrete bundle. Also (re)writes the lockfile when sources are present."""
    data = bundle.load(root)
    extends = data.pop("extends", []) or []
    if not extends:
        return data

    lock = load_lock(root)
    sources: dict = {}
    definitions: dict = {}
    for entry in extends:
        repo, subpath, ref = parse_source(entry)
        pinned = None if update else lock.get("sources", {}).get(entry, {}).get("resolved_commit")
        dest, sha = fetch(repo, pinned or ref)
        content = open(os.path.join(dest, subpath)).read()
        defn = _yaml.load(content) or {}
        if defn.get("id"):
            definitions[defn["id"]] = defn
        sources[entry] = {
            "resolved_commit": sha,
            "ref": ref,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
        }
    save_lock(root, {"lock_version": "1", "sources": sources})

    roles = data.get("sdlc", {}).get("roles", [])
    materialized = []
    for role in roles:
        if isinstance(role, dict) and role.get("use"):
            defn = definitions.get(role["use"])
            if defn is None:
                raise ValueError(
                    f"role uses '{role['use']}' but no extended source provides that id"
                )
            materialized.append(_merge_role(defn, role))
        else:
            materialized.append(role)
    if "sdlc" in data:
        data["sdlc"]["roles"] = materialized

    # standards packs apply globally (no `use:` needed — they're context, not roles)
    std_defs = [d for d in definitions.values() if d.get("kind") == "standard"]
    if std_defs:
        stds = data.setdefault("sdlc", {}).setdefault("standards", [])
        seen = {s.get("id") for s in stds}
        for d in std_defs:
            if d.get("id") not in seen:
                stds.append({"id": d.get("id"), "title": d.get("title", d.get("id")), "rules": d.get("rules", [])})

    # lifecycle packs supply phases + gates (+ loops). Local always wins; if
    # several lifecycle packs are extended, the last one listed wins.
    lifecycle_defs = [d for d in definitions.values() if d.get("kind") == "lifecycle"]
    if lifecycle_defs:
        sdlc = data.setdefault("sdlc", {})
        pack = lifecycle_defs[-1]
        local_lc = sdlc.get("lifecycle") or {}
        if not local_lc.get("phases"):
            sdlc["lifecycle"] = {"phases": pack.get("phases"), "gates": pack.get("gates") or {}}
            if not sdlc.get("loops"):
                sdlc["loops"] = pack.get("loops") or {}
    return data
