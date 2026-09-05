"""Exact arithmetic shared by dialogue parsing and response generation."""
from fractions import Fraction
import re

NUMBER = r"[+-]?(?:\d+/\d+|\d+(?:\.\d+)?)"
EQUATION = re.compile(rf"y=({NUMBER}|[+-]?)x({NUMBER})?(?![\d./])")


def number(value: str) -> Fraction:
    return Fraction(value)


def display(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else str(value)


def equations(text: str) -> tuple[tuple[str, str], ...]:
    result = []
    for match in EQUATION.finditer(re.sub(r"\s+", "", text.lower())):
        slope = {'': '1', '+': '1', '-': '-1'}.get(match[1], match[1])
        try:
            result.append((display(number(slope)), display(number(match[2] or '0'))))
        except (ValueError, ZeroDivisionError):
            continue
    return tuple(result)


def fingerprint(text: str) -> str:
    compact = re.sub(r"[\s，。！？、,:：；;!?]+", "", text.lower())
    return EQUATION.sub(lambda m: str(equations(m[0])), compact)


def spoken_number(value: str) -> Fraction:
    digits = dict(zip('零一二三四五六七八九', range(10)))
    digits['两'] = 2
    if value in digits:
        return Fraction(digits[value])
    if '十' in value:
        tens, units = value.split('十')
        return Fraction((digits[tens] if tens else 1) * 10 + (digits[units] if units else 0))
    return number(value)


def rate_model(text: str) -> tuple[str, str] | None:
    """Recognize an explicit fixed fee + per-unit fee, without guessing rates."""
    amount = r"([零一二两三四五六七八九十\d.]+)元"
    base = re.search(r"(?:起步价|固定费用|基础费用)" + amount, text)
    rate = re.search(r"每(?:公里|件|次)(?:再)?(?:收|加收|收费)?" + amount, text)
    if not (base and rate):
        return None
    try:
        return display(spoken_number(rate[1])), display(spoken_number(base[1]))
    except (ValueError, KeyError, ZeroDivisionError):
        return None
