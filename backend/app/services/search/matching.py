from .tokens import MAX_FUZZY_TOKENS, TRIGRAM_MIN, tokenize, trigrams


def _quote(term: str) -> str:
    return f'"{term.replace(chr(34), chr(34) * 2)}"'


def phrase_match(query: str) -> str:
    return _quote(query.strip())


def or_terms_match(query: str) -> str:
    terms = tokenize(query)
    if not terms:
        return ""
    return " OR ".join(_quote(term) for term in terms)


def prefix_terms_match(query: str) -> str:
    terms = tokenize(query)
    if not terms:
        return ""
    return " ".join(f"{_quote(term)} *" for term in terms)


def trigram_match(query: str) -> str:
    groups: list[str] = []
    for term in tokenize(query):
        if len(term) < TRIGRAM_MIN:
            continue
        trigram_list = trigrams(term)
        if not trigram_list:
            continue
        groups.append("(" + " OR ".join(_quote(t) for t in trigram_list) + ")")
        if len(groups) >= MAX_FUZZY_TOKENS:
            break
    return " AND ".join(groups)
