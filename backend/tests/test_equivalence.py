import pytest
import sympy

from app.math.equivalence import equivalent, parse_math


@pytest.mark.parametrize(
    ("student", "expected", "should_pass"),
    [
        ("2x", "x*2", True),
        ("x^2", "x*x", True),
        ("\\frac{1}{2}", "0.5", True),
        ("sin(x)^2 + cos(x)^2", "1", True),
        ("(x+1)(x-1)", "x^2 - 1", True),
        ("2*x + 3", "2*(x+1)", False),
        ("x^3", "x*x*x", True),
        ("\\pi", "3.141592653589793", True),
        ("e^x", "exp(x)", True),
    ],
)
def test_equivalence_chain(student: str, expected: str, should_pass: bool) -> None:
    result = equivalent(student, expected)
    assert result.equivalent is should_pass, f"{student} vs {expected}: {result}"


def test_equivalence_reports_stage() -> None:
    result = equivalent("2x", "x*2")
    assert result.stage in ("simplify", "sampling")
    bad = equivalent("x+1", "x+2")
    assert bad.equivalent is False
    assert bad.stage == "none"


def test_parse_rejects_garbage() -> None:
    with pytest.raises((SyntaxError, ValueError, TypeError)):
        parse_math("this is not math @@@")
    result = equivalent("@@@", "1")
    assert result.equivalent is False
    assert result.stage == "parse"


def test_solveset_stage_catches_equation_equivalence() -> None:
    result = equivalent("x^2 - 4", "(x-2)(x+2)")
    assert result.equivalent is True


def test_parse_set_values() -> None:
    parsed = parse_math("\\{1, -1, i, -i\\}")
    assert {str(entry) for entry in parsed} == {"1", "-1", "-I", "I"}
    parsed_pi = parse_math("\\{0, pi/2, pi, 3*pi/2\\}")
    assert len(parsed_pi) == 4


def test_set_equivalence_is_order_insensitive() -> None:
    assert equivalent("\\{1, -1, i, -i\\}", "\\{-i, i, -1, 1\\}").equivalent is True
    assert equivalent("\\{0, pi/2, pi, 3*pi/2\\}", "\\{3*pi/2, 0, pi/2, pi\\}").equivalent is True


def test_set_equivalence_rejects_different_sets() -> None:
    assert equivalent("\\{1, -1\\}", "\\{1, i\\}").equivalent is False
    assert equivalent("\\{1, 2\\}", "\\{1, 2, 3\\}").equivalent is False
    assert equivalent("\\{1, 2\\}", "1").equivalent is False


def test_imaginary_unit_lowercase_i() -> None:
    parsed = parse_math("i*x^2 + 1")
    assert "i" not in {symbol.name for symbol in parsed.free_symbols}


def test_divergent_functions_fail_sampling() -> None:
    result = equivalent("sin(x)", "cos(x)")
    assert result.equivalent is False


def test_parse_absolute_values_and_ln() -> None:
    assert equivalent(r"\ln|x-1|", "ln(Abs(x-1))").equivalent is True
    parsed = parse_math(r"\frac{1}{2}\ln|x-1|-\frac{1}{2}\ln|x+1|+C")
    assert "Abs" in str(parsed)
    parsed_delim = parse_math(r"\frac{1}{2}\ln\left|\frac{x-1}{x+1}\right|+C")
    assert "Abs" in str(parsed_delim)


def test_parse_equations_and_systems() -> None:
    parsed = parse_math(r"A=1/2")
    assert parsed == sympy.sympify("A - 1/2")
    system = parse_math(r"A=1/2,\;B=-1/2")
    assert system == sympy.FiniteSet(
        sympy.sympify("A - 1/2"), sympy.sympify("B + 1/2")
    )


def test_equation_system_equivalence_is_order_insensitive() -> None:
    left = equivalent(r"A=1/2,\;B=-1/2", r"B=-1/2, A=1/2")
    assert left.equivalent is True
    right = equivalent(r"A=1/2,\;B=-1/2", r"A=-1/2,\;B=1/2")
    assert right.equivalent is False


def test_equation_text_skips_relational_operators() -> None:
    parsed = parse_math("x>=0")
    assert str(parsed).startswith("x")
