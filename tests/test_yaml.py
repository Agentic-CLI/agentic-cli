"""Tests for agentic._yaml — the load/dump layer with a stdlib fallback parser.

These assertions must hold whether the real PyYAML is installed or the built-in
block-style fallback is in use, so they test observable round-trip behaviour
rather than exact serialization bytes.
"""
from agentic import _yaml


def test_roundtrip_nested_dicts_lists_scalars():
    data = {
        "name": "demo",
        "count": 3,
        "ratio": 1.5,
        "enabled": True,
        "disabled": False,
        "empty": None,
        "nested": {
            "roles": [
                {"id": "a", "caps": ["read", "write"]},
                {"id": "b", "caps": ["read"]},
            ],
            "flags": {"deep": {"deeper": "value"}},
        },
        "list_of_scalars": [1, 2, 3],
    }
    assert _yaml.load(_yaml.dump(data)) == data


def test_string_one_stays_a_string():
    """The crown jewel: a string "1" must NOT become the int 1 after round-trip."""
    out = _yaml.load(_yaml.dump({"v": "1"}))
    assert out["v"] == "1"
    assert isinstance(out["v"], str)


def test_int_one_stays_an_int():
    """The dual of the above: an int 1 must stay an int."""
    out = _yaml.load(_yaml.dump({"v": 1}))
    assert out["v"] == 1
    assert isinstance(out["v"], int)


def test_various_stringy_scalars_survive_as_strings():
    data = {"a": "1", "b": "true", "c": "null", "d": "3.14", "e": "no"}
    out = _yaml.load(_yaml.dump(data))
    assert out == data
    for key in data:
        assert isinstance(out[key], str)


def test_bool_int_float_null_types_preserved():
    data = {"b": True, "i": 42, "f": 2.5, "n": None}
    out = _yaml.load(_yaml.dump(data))
    assert out["b"] is True
    assert isinstance(out["i"], int) and out["i"] == 42
    assert isinstance(out["f"], float) and out["f"] == 2.5
    assert out["n"] is None


def test_inline_flow_list_parses():
    out = _yaml.load("caps: [read, write, bash]\n")
    assert out["caps"] == ["read", "write", "bash"]


def test_inline_flow_map_parses():
    out = _yaml.load("gate: {after: plan, level: high}\n")
    assert out["gate"] == {"after": "plan", "level": "high"}


def test_empty_inline_collections_parse():
    out = _yaml.load("a: []\nb: {}\n")
    assert out["a"] == []
    assert out["b"] == {}


def test_comments_are_stripped():
    text = (
        "# leading comment\n"
        "name: demo   # trailing comment\n"
        "count: 2\n"
        "# another comment\n"
    )
    out = _yaml.load(text)
    assert out == {"name": "demo", "count": 2}


def test_hash_inside_quoted_string_is_not_a_comment():
    out = _yaml.load('color: "#ff0000"\n')
    assert out["color"] == "#ff0000"


def test_block_list_of_maps_roundtrip():
    data = {"roles": [{"id": "eng", "owns": ["src/**"]}, {"id": "rev"}]}
    assert _yaml.load(_yaml.dump(data)) == data


def test_using_pyyaml_flag_is_bool():
    assert isinstance(_yaml.USING_PYYAML, bool)
