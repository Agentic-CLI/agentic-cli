"""Tests for agentic.bundle — the single source of truth: default / validate /
load-save round-trip."""
import os

from agentic import bundle


def test_default_bundle_is_valid():
    data = bundle.default("myproj")
    assert data["name"] == "myproj"
    assert data["schema_version"] == "1"
    assert bundle.validate(data) == []


def test_default_bundle_shape():
    data = bundle.default("x")
    role_ids = [r["id"] for r in data["sdlc"]["roles"]]
    assert "feature-engineer" in role_ids
    assert "reviewer" in role_ids
    assert data["sdlc"]["lifecycle"]["phases"] == [
        "discover", "plan", "implement", "qa", "review", "ship",
    ]
    assert set(data["projections"]) == {"claude-code", "cursor", "agents-md"}


def test_validate_flags_missing_schema_version_and_name():
    errs = bundle.validate({})
    assert "missing schema_version" in errs
    assert "missing name" in errs


def test_validate_flags_empty_roles():
    data = {"schema_version": "1", "name": "n", "sdlc": {"lifecycle": {"phases": ["a"]}}}
    assert "sdlc.roles is empty" in bundle.validate(data)


def test_validate_flags_role_without_id_and_without_capabilities():
    data = {
        "schema_version": "1",
        "name": "n",
        "sdlc": {
            "roles": [{"role": "does things"}],
            "lifecycle": {"phases": ["a"]},
        },
    }
    errs = bundle.validate(data)
    assert "a role is missing 'id'" in errs
    assert any("has no capabilities" in e for e in errs)


def test_validate_flags_empty_lifecycle_phases():
    data = {
        "schema_version": "1",
        "name": "n",
        "sdlc": {"roles": [{"id": "r", "capabilities": ["read"]}]},
    }
    assert "sdlc.lifecycle.phases is empty" in bundle.validate(data)


def test_save_load_roundtrip(tmp_path):
    root = str(tmp_path)
    data = bundle.default("roundtrip-proj")
    bundle.save(root, data)
    assert os.path.exists(bundle.bundle_path(root))
    loaded = bundle.load(root)
    assert loaded == data


def test_load_missing_bundle_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        bundle.load(str(tmp_path))
