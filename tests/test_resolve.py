"""Tests for the git-source pack resolver (extends / use / overrides / lock).

Uses a local git repo fixture — no network."""
from __future__ import annotations

import subprocess

import pytest

from agentic import _yaml, bundle, projector, resolve


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def template(tmp_path):
    """A local git 'client repo' holding one persona, tagged v0.1.0."""
    tpl = tmp_path / "template"
    (tpl / "personas").mkdir(parents=True)
    (tpl / "personas" / "security-reviewer.yaml").write_text(
        'kind: persona\n'
        'id: security-reviewer\n'
        'version: "0.1.0"\n'
        'role: "Adversarial reviewer. Never edits code."\n'
        "capabilities: [read, grep, bash]\n"
        'refuses:\n  - "secrets in code"\n  - "auth bypass"\n'
    )
    (tpl / "packs").mkdir()
    (tpl / "packs" / "payments-invariants.yaml").write_text(
        "kind: standard\n"
        "id: payments-invariants\n"
        'version: "0.1.0"\n'
        'title: "Payment platform invariants"\n'
        "rules:\n"
        '  - "Idempotency at the datastore for every money mutation"\n'
        '  - "No floats for money — integer minor units only"\n'
        '  - "Fail closed on compliance checks"\n'
    )
    (tpl / "lifecycles").mkdir()
    (tpl / "lifecycles" / "staff-sdlc.yaml").write_text(
        "kind: lifecycle\n"
        "id: staff-sdlc\n"
        'version: "0.1.0"\n'
        "phases: [discover, plan, implement, qa, review, ship]\n"
        "gates:\n"
        "  definition_of_ready: { after: plan, requires: [plan_note] }\n"
        "  definition_of_done:  { after: ship, requires: [test_evidence, review_pass] }\n"
        "loops:\n"
        "  implement: { until: tests_pass, max_attempts: 3, on_exhausted: relay }\n"
    )
    _git(["init", "-q", "-b", "main"], tpl)
    _git(["add", "-A"], tpl)
    _git(["-c", "user.name=T", "-c", "user.email=t@t", "commit", "-qm", "init"], tpl)
    _git(["tag", "v0.1.0"], tpl)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tpl, capture_output=True, text=True
    ).stdout.strip()
    return tpl, sha


# ───────────────────────────────────────────────── parse_source
@pytest.mark.parametrize(
    "entry,expected",
    [
        ("git::https://github.com/a/b//personas/x.yaml@v1", ("https://github.com/a/b", "personas/x.yaml", "v1")),
        ("git::file:///abs/repo//sub/f.yaml@main", ("file:///abs/repo", "sub/f.yaml", "main")),
        ("git::https://h/a/b//p", ("https://h/a/b", "p", None)),
    ],
)
def test_parse_source(entry, expected):
    assert resolve.parse_source(entry) == expected


def test_parse_source_rejects_non_git():
    with pytest.raises(ValueError):
        resolve.parse_source("https://github.com/a/b//x")


# ───────────────────────────────────────────────── yaml regression
def test_quoted_list_item_with_colons_roundtrips():
    """The bug that broke extends: a quoted scalar containing ':' must stay a string."""
    data = {"extends": ["git::file:///x/repo//p/f.yaml@v1"]}
    back = _yaml.load(_yaml.dump(data))
    assert back == data
    assert isinstance(back["extends"][0], str)


# ───────────────────────────────────────────────── effective_bundle
def _project(tmp_path, source):
    proj = tmp_path / "proj"
    (proj / ".agentic").mkdir(parents=True)
    bundle.save(
        str(proj),
        {
            "schema_version": "1",
            "name": "proj",
            "extends": [source],
            "sdlc": {
                "roles": [
                    {"use": "security-reviewer", "owns": ["src/**"], "overrides": {"refuses": ["floats for money"]}}
                ],
                "lifecycle": {"phases": ["plan", "ship"]},
            },
            "projections": ["claude-code"],
        },
    )
    return proj


def test_effective_bundle_materializes_and_locks(tmp_path, template, monkeypatch):
    tpl, sha = template
    monkeypatch.setenv("AGENTIC_CACHE", str(tmp_path / "cache"))
    source = f"git::file://{tpl}//personas/security-reviewer.yaml@v0.1.0"
    proj = _project(tmp_path, source)

    eff = resolve.effective_bundle(str(proj))
    role = eff["sdlc"]["roles"][0]

    # persona materialized from the template
    assert role["id"] == "security-reviewer"
    assert role["capabilities"] == ["read", "grep", "bash"]
    # local field applied
    assert role["owns"] == ["src/**"]
    # override merged into the inherited list
    assert "secrets in code" in role["refuses"]
    assert "floats for money" in role["refuses"]
    # extends is consumed
    assert "extends" not in eff

    # lockfile pins the resolved commit sha
    lock = resolve.load_lock(str(proj))
    entry = lock["sources"][source]
    assert entry["resolved_commit"] == sha
    assert entry["ref"] == "v0.1.0"
    assert len(entry["content_sha256"]) == 64

    # the materialized persona projects into a harness file
    files = projector.render(eff)
    assert any(p.endswith("security-reviewer.md") for p in files)


def test_effective_bundle_offline_uses_lock(tmp_path, template, monkeypatch):
    """After a lock exists, resolution reuses the pinned commit without needing the ref."""
    tpl, sha = template
    monkeypatch.setenv("AGENTIC_CACHE", str(tmp_path / "cache"))
    source = f"git::file://{tpl}//personas/security-reviewer.yaml@v0.1.0"
    proj = _project(tmp_path, source)
    resolve.effective_bundle(str(proj))  # writes lock
    # second resolve still works and keeps the same pinned sha
    resolve.effective_bundle(str(proj))
    assert resolve.load_lock(str(proj))["sources"][source]["resolved_commit"] == sha


def test_standard_pack_applies_globally(tmp_path, template, monkeypatch):
    tpl, _sha = template
    monkeypatch.setenv("AGENTIC_CACHE", str(tmp_path / "cache"))
    source = f"git::file://{tpl}//packs/payments-invariants.yaml@v0.1.0"
    proj = tmp_path / "proj"
    (proj / ".agentic").mkdir(parents=True)
    bundle.save(
        str(proj),
        {
            "schema_version": "1",
            "name": "proj",
            "extends": [source],
            "sdlc": {
                "roles": [{"id": "eng", "capabilities": ["edit"]}],
                "lifecycle": {"phases": ["ship"]},
            },
            "projections": ["claude-code", "cursor", "agents-md"],
        },
    )
    eff = resolve.effective_bundle(str(proj))

    stds = eff["sdlc"]["standards"]
    assert any(s["id"] == "payments-invariants" for s in stds)
    assert any("no floats" in r.lower() for s in stds for r in s["rules"])

    files = projector.render(eff)
    assert "Payment platform invariants" in files["AGENTS.md"]
    assert any(p.endswith("standards.mdc") for p in files)


def test_lifecycle_pack_applies_when_no_local_phases(tmp_path, template, monkeypatch):
    tpl, _sha = template
    monkeypatch.setenv("AGENTIC_CACHE", str(tmp_path / "cache"))
    source = f"git::file://{tpl}//lifecycles/staff-sdlc.yaml@v0.1.0"
    proj = tmp_path / "proj"
    (proj / ".agentic").mkdir(parents=True)
    bundle.save(
        str(proj),
        {
            "schema_version": "1",
            "name": "proj",
            "extends": [source],
            "sdlc": {"roles": [{"id": "eng", "capabilities": ["edit"]}]},
            "projections": ["claude-code"],
        },
    )
    eff = resolve.effective_bundle(str(proj))

    lc = eff["sdlc"]["lifecycle"]
    assert lc["phases"] == ["discover", "plan", "implement", "qa", "review", "ship"]
    assert lc["gates"]["definition_of_ready"]["after"] == "plan"
    assert lc["gates"]["definition_of_done"]["requires"] == ["test_evidence", "review_pass"]
    assert eff["sdlc"]["loops"]["implement"]["max_attempts"] == 3


def test_lifecycle_pack_local_phases_win(tmp_path, template, monkeypatch):
    tpl, _sha = template
    monkeypatch.setenv("AGENTIC_CACHE", str(tmp_path / "cache"))
    source = f"git::file://{tpl}//lifecycles/staff-sdlc.yaml@v0.1.0"
    proj = tmp_path / "proj"
    (proj / ".agentic").mkdir(parents=True)
    bundle.save(
        str(proj),
        {
            "schema_version": "1",
            "name": "proj",
            "extends": [source],
            "sdlc": {
                "roles": [{"id": "eng", "capabilities": ["edit"]}],
                "lifecycle": {"phases": ["plan", "ship"]},
            },
            "projections": ["claude-code"],
        },
    )
    eff = resolve.effective_bundle(str(proj))

    # local lifecycle wins — the pack does not override it
    assert eff["sdlc"]["lifecycle"]["phases"] == ["plan", "ship"]
    assert "gates" not in eff["sdlc"]["lifecycle"]
    assert "loops" not in eff["sdlc"]


def test_missing_use_definition_raises(tmp_path, template, monkeypatch):
    tpl, _sha = template
    monkeypatch.setenv("AGENTIC_CACHE", str(tmp_path / "cache"))
    source = f"git::file://{tpl}//personas/security-reviewer.yaml@v0.1.0"
    proj = tmp_path / "proj"
    (proj / ".agentic").mkdir(parents=True)
    bundle.save(
        str(proj),
        {
            "schema_version": "1",
            "name": "proj",
            "extends": [source],
            "sdlc": {"roles": [{"use": "does-not-exist"}], "lifecycle": {"phases": ["ship"]}},
        },
    )
    with pytest.raises(ValueError):
        resolve.effective_bundle(str(proj))
