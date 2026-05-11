from typing import Protocol, runtime_checkable


@runtime_checkable
class FuzzyMatcher(Protocol):
    """Port for a fuzzy-string-matching engine.

    Implementations return a similarity score in the 0..100 range. The
    domain has no preference for a specific algorithm; the adapter
    chooses (e.g. ``rapidfuzz.fuzz.WRatio``).
    """

    def score(self, query: str, candidate: str) -> float: ...
