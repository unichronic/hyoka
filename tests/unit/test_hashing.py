from hyoka_schemas.hashing import content_hash


def test_content_hash_is_stable_for_key_order() -> None:
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})

