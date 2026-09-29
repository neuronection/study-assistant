"""Query compilers for the search tiers (ADR-0022 S3 dialect twins).

Every builder returns a :class:`Match` carrying the fts5 MATCH expression for
SQLite and a safe, bind-parameterised PostgreSQL fragment. User text never
reaches SQL or tsquery syntax unquoted: it either travels as a bound parameter
(``:match_text``, ``:t0`` …) or through ``tokens.tokenize``.
"""

from typing import Any, NamedTuple

from .tokens import MAX_FUZZY_TOKENS, TRIGRAM_MIN, tokenize, trigrams

# PostgreSQL combines tsqueries with ``||`` (OR) / ``&&`` (AND) — the old
# single-character ``|`` / ``&`` operators were renamed in the 16.x series and
# no longer exist on current PostgreSQL 16 servers.
_TS_OR = " || "
_TS_AND = " && "

# Candidate threshold for the PostgreSQL trigram tier. The SQL shape is
# ``search_text % :match OR similarity(search_text, :match) >= threshold``
# (pg's own ``%`` uses the server default of 0.3, kept as an extra disjunct).
# Whole-column similarity dilutes with document length, so the tunable
# threshold is lowered for recall parity with the SQLite trigram tier; the
# shared ``fuzzy_text_match`` post-filter carries precision. Measured against
# the twin test corpora: 'derivatve' 0.140, 'calclus' 0.146, 'limts' 0.091 -
# non-matches ('xylophone') stay at 0.00-0.03.
PG_TRIGRAM_SIMILARITY = 0.08


class PgMatch(NamedTuple):
    """PostgreSQL match fragment: SQL snippet plus its bind parameters.

    ``kind`` is ``"tsquery"`` for the tsvector tiers (``sql`` is a tsquery
    expression, consumed by ``tsv @@ …``, ``ts_rank(…)``, ``ts_headline(…)``)
    or ``"trigram"`` for the pg_trgm tier (``sql`` is a self-contained boolean
    predicate over ``search_text``).
    """

    sql: str
    params: dict[str, Any]
    kind: str = "tsquery"


class Match(NamedTuple):
    """A query compiled for both SQL dialects."""

    fts5: str
    pg: PgMatch

    @property
    def is_empty(self) -> bool:
        return not self.fts5 and not self.pg.sql


def _quote(term: str) -> str:
    return f'"{term.replace(chr(34), chr(34) * 2)}"'


def _pg_token(term: str) -> str:
    """Token for a bound tsquery parameter — quotes doubled so nothing in the
    value can terminate the tsquery lexeme even if it is ever inlined."""
    return term.replace("'", "''")


def _pg_tsquery(terms: list[str], operator: str) -> PgMatch:
    params = {f"t{index}": value for index, value in enumerate(terms)}
    sql = operator.join(f"to_tsquery('simple', :t{index})" for index in range(len(terms)))
    return PgMatch(sql=sql, params=params)


def phrase_match(query: str) -> Match:
    raw = query.strip()
    return Match(
        fts5=_quote(raw),
        pg=PgMatch(sql="phraseto_tsquery('simple', :match_text)", params={"match_text": raw}),
    )


def or_terms_match(query: str) -> Match:
    terms = tokenize(query)
    if not terms:
        return Match(fts5="", pg=PgMatch(sql="", params={}))
    return Match(
        fts5=" OR ".join(_quote(term) for term in terms),
        pg=_pg_tsquery([_pg_token(term) for term in terms], _TS_OR),
    )


def prefix_terms_match(query: str) -> Match:
    terms = tokenize(query)
    if not terms:
        return Match(fts5="", pg=PgMatch(sql="", params={}))
    return Match(
        fts5=" ".join(f"{_quote(term)} *" for term in terms),
        pg=_pg_tsquery([_pg_token(term) + ":*" for term in terms], _TS_AND),
    )


def trigram_match(query: str) -> Match:
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
    if not groups:
        return Match(fts5="", pg=PgMatch(sql="", params={}, kind="trigram"))
    return Match(
        fts5=" AND ".join(groups),
        pg=PgMatch(
            sql=(
                "(search_text % :match "
                f"OR similarity(search_text, :match) >= {PG_TRIGRAM_SIMILARITY})"
            ),
            params={"match": query.strip()},
            kind="trigram",
        ),
    )
