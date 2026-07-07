"""Tests for agentic.util — ULIDs, glob matching, hash chaining, project root."""
import os
import time

from agentic import util

_CROCKFORD = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")


def test_ulid_is_26_crockford_chars():
    u = util.ulid()
    assert len(u) == 26
    assert set(u) <= _CROCKFORD


def test_ulid_is_unique():
    ids = {util.ulid() for _ in range(1000)}
    assert len(ids) == 1000


def test_ulid_is_time_sortable():
    """ULIDs minted later must sort lexicographically after earlier ones."""
    first = util.ulid()
    time.sleep(0.005)
    second = util.ulid()
    assert first < second


def test_glob_single_star_matches_one_segment():
    assert util.glob_match("src/*.py", "src/api.py")
    assert not util.glob_match("src/*.py", "src/todo/api.py")


def test_glob_double_star_matches_any_depth():
    assert util.glob_match("**/models/**", "src/todo/models/todo.py")
    assert util.glob_match("**/models/**", "a/b/c/models/x/y.py")
    assert not util.glob_match("**/models/**", "src/todo/api.py")


def test_glob_substring_pattern():
    assert util.glob_match("**/*schema*", "db/user_schema.sql")
    assert util.glob_match("**/*migration*", "app/db/0001_migration.py")
    assert not util.glob_match("**/*schema*", "app/models/todo.py")


def test_glob_normalizes_backslashes_and_leading_dotslash():
    assert util.glob_match("src/*.py", "./src/api.py")
    assert util.glob_match("src/*.py", "src\\api.py")


def test_glob_dot_in_pattern_is_literal():
    assert util.glob_match("a.txt", "a.txt")
    assert not util.glob_match("a.txt", "aXtxt")


def test_chain_hash_ignores_existing_hash_field():
    entry = {"seq": 0, "event": "x"}
    h1 = util.chain_hash("prev", entry)
    entry_with_hash = dict(entry, hash="stale-value-should-be-ignored")
    h2 = util.chain_hash("prev", entry_with_hash)
    assert h1 == h2


def test_chain_hash_depends_on_prev_and_body():
    base = {"seq": 1, "event": "e"}
    assert util.chain_hash("A", base) != util.chain_hash("B", base)
    assert util.chain_hash("A", base) != util.chain_hash("A", {"seq": 2, "event": "e"})


def test_chain_hash_is_sha256_hex():
    h = util.chain_hash("0" * 64, {"a": 1})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_canonical_is_stable_regardless_of_key_order():
    assert util.canonical({"b": 1, "a": 2}) == util.canonical({"a": 2, "b": 1})


def test_find_project_root_walks_up_to_agentic(tmp_path):
    root = tmp_path / "proj"
    (root / ".agentic").mkdir(parents=True)
    deep = root / "src" / "pkg" / "sub"
    deep.mkdir(parents=True)
    assert util.find_project_root(str(deep)) == str(root)


def test_find_project_root_returns_none_when_absent(tmp_path):
    lonely = tmp_path / "nowhere"
    lonely.mkdir()
    assert util.find_project_root(str(lonely)) is None
