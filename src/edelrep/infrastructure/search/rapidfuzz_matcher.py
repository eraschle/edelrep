from rapidfuzz import fuzz


class RapidFuzzMatcher:
    """FuzzyMatcher adapter using rapidfuzz's WRatio (0..100)."""

    def score(self, query: str, candidate: str) -> float:
        if not query or not candidate:
            return 0.0
        return float(fuzz.WRatio(query, candidate))
