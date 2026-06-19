"""Run: env -u GIT_INDEX_FILE .venv/bin/python -m pytest tests/unit/test_threeway_canon.py -q"""
import pytest
from threeway.canon import canonicalize


def test_returns_bytes():
    assert isinstance(canonicalize({"a": 1}), bytes)


def test_key_order_is_lexicographic_and_independent_of_input_order():
    a = canonicalize({"b": 2, "a": 1})
    b = canonicalize({"a": 1, "b": 2})
    assert a == b == b'{"a":1,"b":2}'


def test_nested_objects_canonicalize_deterministically():
    obj = {"z": [3, 2, 1], "a": {"y": 1, "x": 2}}
    assert canonicalize(obj) == b'{"a":{"x":2,"y":1},"z":[3,2,1]}'


def test_unicode_is_preserved_not_ascii_escaped():
    # RFC 8785 keeps UTF-8; it does not \u-escape printable non-ASCII.
    assert canonicalize({"k": "café"}) == '{"k":"café"}'.encode("utf-8")


def test_non_serializable_raises():
    with pytest.raises(Exception):
        canonicalize({"k": object()})
