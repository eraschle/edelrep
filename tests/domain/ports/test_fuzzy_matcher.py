from edelrep.domain.ports import FuzzyMatcher


class _DummyMatcher:
    def score(self, query: str, candidate: str) -> float:
        return 100.0 if query == candidate else 0.0


def test_fuzzy_matcher_protocol_runtime_check() -> None:
    matcher: FuzzyMatcher = _DummyMatcher()
    assert isinstance(matcher, FuzzyMatcher)
    assert matcher.score("a", "a") == 100.0
    assert matcher.score("a", "b") == 0.0
