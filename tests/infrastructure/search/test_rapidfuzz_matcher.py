from edelrep.infrastructure.search.rapidfuzz_matcher import RapidFuzzMatcher


def test_identical_strings_score_100() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("hello", "hello") == 100.0


def test_completely_different_strings_score_low() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("abc", "xyz123") < 30.0


def test_one_char_typo_scores_high() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("Mercedes", "Mercades") >= 80.0


def test_empty_query_returns_zero() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("", "anything") == 0.0


def test_empty_candidate_returns_zero() -> None:
    matcher = RapidFuzzMatcher()
    assert matcher.score("query", "") == 0.0
