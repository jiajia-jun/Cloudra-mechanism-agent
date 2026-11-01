"""Chemical distinctions shared by graph coverage and answer matching.

Only explicit, mutually exclusive declarations restrict a candidate. Missing
labels retain the existing matching behavior; IDs and numerical Gold answers
never establish a pathway or electronic-state identity.
"""

from __future__ import annotations


def _words(value: str | None) -> list[str]:
    return "".join(
        character if character.isalnum() else " "
        for character in (value or "").casefold()
    ).split()


def _rotation_channel(value: str | None) -> str | None:
    words = set(_words(value))
    channels = [
        name for name, variants in (
            ("disrotatory", {"disrotatory", "disrotation"}),
            ("conrotatory", {"conrotatory", "conrotation"}),
        ) if words & variants
    ]
    return channels[0] if len(channels) == 1 else None


def channel_compatible(
    expected: str | None, observed: str | None, *, require_exact: bool = False,
) -> bool:
    if require_exact:
        return observed == expected
    target, candidate = _rotation_channel(expected), _rotation_channel(observed)
    return target is None or candidate is None or target == candidate


def state_compatible(expected: str | None, observed: str | None) -> bool:
    def identity(value):
        words = _words(value)
        spins = set(words) & {"singlet", "triplet"}
        shells = {
            name for name in ("open", "closed")
            if name + "shell" in words
            or any(left == name and right == "shell" for left, right in zip(words, words[1:]))
        }
        return (next(iter(spins)) if len(spins) == 1 else None,
                next(iter(shells)) if len(shells) == 1 else None)

    return all(
        target is None or candidate is None or target == candidate
        for target, candidate in zip(identity(expected), identity(observed))
    )
