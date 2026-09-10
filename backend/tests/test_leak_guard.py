from app.ai.contracts.contracts import Constraint, hint_contract, validate
from app.math.leak_guard import check_leak, extract_math


def test_extract_math_finds_all_forms() -> None:
    text = "Use $u = x^2$ then $$\\sin(x)$$ and 42 more"
    found = extract_math(text)
    assert "u = x^2" in found
    assert "\\sin(x)" in found
    assert "42" in found


def test_leak_guard_catches_equivalent_expression() -> None:
    leak = check_leak("Try writing it as $x \\cdot x$ instead.", "x^2")
    assert leak.leaks is True
    assert leak.expression == "x \\cdot x"


def test_leak_guard_catches_direct_answer() -> None:
    leak = check_leak("The answer is $2x + 3$.", "3 + 2x")
    assert leak.leaks is True


def test_leak_guard_allows_general_hint() -> None:
    safe = check_leak(
        "Think about the product rule: how would you differentiate a product of two functions?",
        "2*x*sin(x) + x**2*cos(x)",
    )
    assert safe.leaks is False


def test_leak_guard_ignores_small_numbers() -> None:
    safe = check_leak(
        "Take the 2 functions and multiply their derivatives carefully.", "x^2*sin(x)"
    )
    assert safe.leaks is False


def test_hint_contract_blocks_leaking_hint() -> None:
    context = {"expected": "x^2"}
    leaking = validate("Just write $x\\cdot x$ and you are done.", hint_contract(2), context)
    assert not leaking.ok
    assert any("no_answer_reveal" in violation.constraint for violation in leaking.violations)


def test_hint_contract_enforces_word_budget() -> None:
    context = {"expected": "x^2"}
    long_hint = "word " * 120
    result = validate(long_hint, hint_contract(1), context)
    assert not result.ok


def test_hint_contract_level_five_allows_answer() -> None:
    context = {"expected": None}
    worked = validate("Full solution: $x \\cdot x$ therefore $x^2$.", hint_contract(5), context)
    assert worked.ok


def test_validate_without_expected_skips_reveal_check() -> None:
    result = validate("contains $x^2$ freely", [Constraint("no_answer_reveal")], {})
    assert result.ok
