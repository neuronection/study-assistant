from difflib import SequenceMatcher

from .tokens import tokenize

FUZZY_RATIO_CUTOFF = 0.8
MIN_FUZZY_TOKEN_LEN = 3


def _token_matches(needle: str, token: str) -> bool:
    if needle in token:
        return True
    return SequenceMatcher(None, needle, token).ratio() >= FUZZY_RATIO_CUTOFF


def fuzzy_text_match(query: str, text: str) -> bool:
    needles = [t for t in tokenize(query) if len(t) >= MIN_FUZZY_TOKEN_LEN]
    if not needles:
        return False
    haystack = tokenize(text, drop_stopwords=False)
    return all(
        any(_token_matches(needle, token) for token in haystack) for needle in needles
    )
