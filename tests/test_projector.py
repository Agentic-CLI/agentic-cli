"""Tests for agentic.projector — compile a bundle into harness-native config and
detect drift on hand-edited generated files."""
import os

from agentic import bundle, projector


def _default():
    return bundle.default("demo")


# ------------------------------------------------------------------- render
def test_render_default_produces_all_expected_files():
    files = projector.render(_default())
    expected = {
        os.path.join(".claude", "agents", "feature-engineer.md"),
        os.path.join(".claude", "agents", "reviewer.md"),
        os.path.join(".claude", "skills", "discover", "SKILL.md"),
        os.path.join(".claude", "skills", "ship", "SKILL.md"),
        os.path.join(".claude", "settings.json"),
        os.path.join(".cursor", "rules", "feature-engineer.mdc"),
        os.path.join(".cursor", "rules", "lifecycle.mdc"),
        "AGENTS.md",
    }
    assert expected <= set(files)


def test_render_emits_a_skill_per_phase():
    data = _default()
    files = projector.render(data)
    for phase in data["sdlc"]["lifecycle"]["phases"]:
        assert os.path.join(".claude", "skills", phase, "SKILL.md") in files


def test_generated_files_carry_the_marker():
    files = projector.render(_default())
    agent_md = files[os.path.join(".claude", "agents", "feature-engineer.md")]
    assert projector.MARKER in agent_md
    assert projector.MARKER in files["AGENTS.md"]


def test_agent_md_maps_capabilities_to_claude_tools():
    files = projector.render(_default())
    fe = files[os.path.join(".claude", "agents", "feature-engineer.md")]
    # feature-engineer caps: read, edit, write, bash
    assert "tools: Read, Edit, Write, Bash" in fe


def test_claude_settings_wires_gate_hook():
    import json

    files = projector.render(_default())
    settings = json.loads(files[os.path.join(".claude", "settings.json")])
    hook_cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert hook_cmd.endswith("gate")
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "Edit|Write|MultiEdit"


def test_skill_md_shows_gate_after_plan():
    files = projector.render(_default())
    plan_skill = files[os.path.join(".claude", "skills", "plan", "SKILL.md")]
    assert "definition_of_ready" in plan_skill
    discover_skill = files[os.path.join(".claude", "skills", "discover", "SKILL.md")]
    assert "Gate after this phase" not in discover_skill


def test_cursor_owned_role_uses_globs_others_always_apply():
    files = projector.render(_default())
    fe = files[os.path.join(".cursor", "rules", "feature-engineer.mdc")]
    rev = files[os.path.join(".cursor", "rules", "reviewer.mdc")]
    assert "globs: src/**" in fe
    assert "alwaysApply: false" in fe
    assert "alwaysApply: true" in rev  # reviewer owns nothing


# ------------------------------------------------------------- projections
def test_dropping_cursor_target_omits_cursor_files():
    data = _default()
    data["projections"] = ["claude-code", "agents-md"]
    files = projector.render(data)
    assert not any(rel.startswith(".cursor") for rel in files)
    assert "AGENTS.md" in files
    assert os.path.join(".claude", "settings.json") in files


def test_dropping_claude_code_omits_claude_files():
    data = _default()
    data["projections"] = ["agents-md"]
    files = projector.render(data)
    assert set(files) == {"AGENTS.md"}


# ------------------------------------------------------------------- drift
def test_project_writes_files_and_no_initial_drift(tmp_path):
    root = str(tmp_path)
    data = _default()
    projector.project(root, data)
    assert os.path.exists(os.path.join(root, "AGENTS.md"))
    assert projector.check_drift(root, data) == []


def test_check_drift_detects_hand_edited_file(tmp_path):
    root = str(tmp_path)
    data = _default()
    projector.project(root, data)
    edited_rel = os.path.join(".claude", "agents", "reviewer.md")
    with open(os.path.join(root, edited_rel), "a") as f:
        f.write("\nhand-edited line that should never survive\n")
    drift = projector.check_drift(root, data)
    assert f"{edited_rel} (edited)" in drift


def test_check_drift_detects_missing_file(tmp_path):
    root = str(tmp_path)
    data = _default()
    projector.project(root, data)
    missing_rel = os.path.join(".claude", "settings.json")
    os.remove(os.path.join(root, missing_rel))
    drift = projector.check_drift(root, data)
    assert f"{missing_rel} (missing)" in drift
