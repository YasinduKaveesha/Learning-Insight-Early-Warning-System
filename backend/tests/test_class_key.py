"""Class-key generation rules (D1; plan section 4.2, docs/04 section 3.1).

Gate 5 of work order B3.2: across >= 10,000 generated keys the generator never emits a
visually ambiguous character (`0`, `O`, `1`, `I`) or a run of six identical characters.
"""

from __future__ import annotations

from app.application.class_key import (
    CLASS_KEY_ALPHABET,
    CLASS_KEY_LENGTH,
    CLASS_KEY_RE,
    generate_class_key,
)

_AMBIGUOUS = {"0", "O", "1", "I"}
_SAMPLE = 10_000


def test_alphabet_is_32_unambiguous_symbols() -> None:
    assert len(CLASS_KEY_ALPHABET) == 32
    assert len(set(CLASS_KEY_ALPHABET)) == 32
    assert _AMBIGUOUS.isdisjoint(CLASS_KEY_ALPHABET)
    # 0-9A-Z minus the four ambiguous glyphs.
    expected = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ") - _AMBIGUOUS
    assert set(CLASS_KEY_ALPHABET) == expected


def test_generated_keys_are_well_formed_and_unambiguous() -> None:
    for _ in range(_SAMPLE):
        key = generate_class_key()
        assert len(key) == CLASS_KEY_LENGTH
        assert CLASS_KEY_RE.match(key), key
        assert _AMBIGUOUS.isdisjoint(key), key
        assert set(key) <= set(CLASS_KEY_ALPHABET), key
        assert len(set(key)) > 1, f"six identical characters: {key}"


def test_generator_explores_the_space() -> None:
    # Not a distribution test -- just a guard that the sample is not a stuck constant.
    keys = {generate_class_key() for _ in range(_SAMPLE)}
    assert len(keys) > _SAMPLE * 0.99


def test_format_regex_permits_ambiguous_glyphs_at_rest() -> None:
    # The DB CHECK is `^[0-9A-Z]{6}$` on purpose -- excluding 0/O/1/I is a generation rule,
    # not a storage rule. A key with a zero is still storage-valid.
    assert CLASS_KEY_RE.match("0OO1II")
    assert not CLASS_KEY_RE.match("abc123")
    assert not CLASS_KEY_RE.match("ABC12")
    assert not CLASS_KEY_RE.match("ABC123X")
