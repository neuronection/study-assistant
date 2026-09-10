import re

TOKEN_SPLIT = re.compile(r"[^0-9a-zA-Z\u03b1-\u03c9\u0391-\u03a9]+")

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "what", "how", "why", "when",
    "of", "in", "to", "for", "and", "or", "on", "do", "does", "did", "with",
    "about", "tell", "me", "explain", "please", "can", "you", "your", "it",
    "this", "that", "be", "by", "at", "as", "from",
}

TRIGRAM_MIN = 3
MAX_FUZZY_TOKENS = 6


def tokenize(query: str, *, drop_stopwords: bool = True) -> list[str]:
    terms = [
        term
        for term in TOKEN_SPLIT.split(query.lower())
        if len(term) > 1 and (not drop_stopwords or term not in STOPWORDS)
    ]
    return terms[:12]


def trigrams(token: str) -> list[str]:
    return [token[i : i + 3] for i in range(len(token) - 2)]
