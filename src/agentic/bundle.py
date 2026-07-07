"""Load / validate / scaffold the bundle — the one source of truth."""
from __future__ import annotations

import os

from . import _yaml

BUNDLE_REL = os.path.join(".agentic", "bundle.yaml")


def bundle_path(root: str) -> str:
    return os.path.join(root, BUNDLE_REL)


def load(root: str) -> dict:
    with open(bundle_path(root)) as f:
        return _yaml.load(f.read()) or {}


def save(root: str, data: dict) -> None:
    os.makedirs(os.path.dirname(bundle_path(root)), exist_ok=True)
    with open(bundle_path(root), "w") as f:
        f.write(_yaml.dump(data))


def validate(data: dict) -> list[str]:
    errs = []
    if not data.get("schema_version"):
        errs.append("missing schema_version")
    if not data.get("name"):
        errs.append("missing name")
    sdlc = data.get("sdlc") or {}
    if not sdlc.get("roles"):
        errs.append("sdlc.roles is empty")
    for r in sdlc.get("roles", []):
        if not r.get("id"):
            errs.append("a role is missing 'id'")
        caps = r.get("capabilities") or []
        if not caps:
            errs.append(f"role {r.get('id')} has no capabilities")
    lifecycle = sdlc.get("lifecycle") or {}
    if not lifecycle.get("phases"):
        errs.append("sdlc.lifecycle.phases is empty")
    return errs


def default(name: str) -> dict:
    """A sensible starter bundle: a builder, an independent reviewer, the
    standard lifecycle with two gates, and a sensitivity rule that guards the
    data model / auth / migrations."""
    return {
        "schema_version": "1",
        "name": name,
        "sdlc": {
            "roles": [
                {
                    "id": "feature-engineer",
                    "role": "Build the feature end to end; write tests; keep changes small and reversible.",
                    "owns": ["src/**"],
                    "capabilities": ["read", "edit", "write", "bash"],
                    "pairs_with": ["reviewer"],
                },
                {
                    "id": "reviewer",
                    "role": "Independently review for correctness first, then simplification. Never edits code.",
                    "capabilities": ["read", "grep", "bash"],
                },
            ],
            "lifecycle": {
                "phases": ["discover", "plan", "implement", "qa", "review", "ship"],
                "gates": {
                    "definition_of_ready": {"after": "plan", "requires": ["plan_note"]},
                    "definition_of_done": {"after": "ship", "requires": ["test_evidence", "review_pass"]},
                },
            },
            "sensitivity": {
                "rules": [
                    {
                        "match": {"paths": ["**/models/**", "**/*schema*", "**/auth/**", "**/*migration*"]},
                        "level": "sensitive",
                        "require": ["adversarial_review", "human_relay"],
                    }
                ]
            },
        },
        "projections": ["claude-code", "agents-md"],
    }
