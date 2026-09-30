"""Bounded steepness assertions evaluated with exact |k| arithmetic.

Unrecognized language is left unscored; missing sign/range conditions are not
silently treated as a correct principle or as the b-controls-slope misconception.
"""
from dataclasses import dataclass
import re

from .clause_splitter import split_linear_clauses
from .linear_math import NUMBER, equations, number


@dataclass(frozen=True)
class SlopeAssessment:
    claims: tuple[tuple[str, bool | None], ...] = ()

    @property
    def status(self) -> str:
        values = [truth for _, truth in self.claims]
        if False in values:
            return "incorrect"
        if None in values:
            return "insufficient_conditions"
        return "correct" if values else "not_applicable"


_RELATION = re.compile(r"一样陡|同样陡|更平缓|越平缓|更平坦|更陡|越陡|变陡")
_CHANGE = r"越大|变大|增大|增加|越小|变小|减小"


def _relation(tail: str) -> tuple[int | None, bool] | None:
    # Another subject starts a new assertion, even without punctuation.
    tail = re.split(r"(?:[，,]?b|[，,]?k(?!的绝对值))", tail, maxsplit=1)[0]
    match = _RELATION.search(tail)
    if not match:
        return None
    if re.search(r"不一定|未必|可能", tail[:match.end()]):
        return None, False
    expected = 0 if match[0] in {"一样陡", "同样陡"} else -1 if "平" in match[0] else 1
    denied = bool(re.search(r"(?:没有|并不|不会|不)(?:变得|变|会)?$", tail[:match.start()]))
    return expected, denied


def _matches_change(actual: int, relation: tuple[int | None, bool]) -> bool | None:
    expected, denied = relation
    if expected is None:
        return None
    return (actual != expected) if denied else (actual == expected)


def _sign(value) -> int:
    return (value > 0) - (value < 0)


def assess_slope_claims(text: str, context: str = "") -> SlopeAssessment:
    claims = []
    for clause in split_linear_clauses(text.replace("＋", "+").replace("−", "-")):
        if re.search(r"[?？]|是否|是不是|对不对|(?:有同学|有人|有些同学).{0,6}(?:说|认为|觉得|问)", clause):
            continue
        transitions = list(re.finditer(
            rf"k(?:从|由)({NUMBER})(?:变成|变为|变到|增大到|增加到|减小到|到)({NUMBER})(?![\d./])", clause
        ))
        for index, transition in enumerate(transitions):
            end = transitions[index + 1].start() if index + 1 < len(transitions) else len(clause)
            relation = _relation(clause[transition.end():end])
            if relation:
                try:
                    change = _sign(abs(number(transition[2])) - abs(number(transition[1])))
                    claims.append(("k:steepness", _matches_change(change, relation)))
                except (ValueError, ZeroDivisionError):
                    claims.append(("k:steepness", None))
        for magnitude in re.finditer(rf"(?:\|k\||k的?绝对值|斜率的?绝对值)({_CHANGE})", clause):
            relation = _relation(clause[magnitude.end():])
            if relation:
                change = -1 if "小" in magnitude[1] else 1
                claims.append(("k:steepness", _matches_change(change, relation)))
        for monotonic in re.finditer(rf"k({_CHANGE})", clause):
            relation = _relation(clause[monotonic.end():])
            if relation:
                direction = -1 if "小" in monotonic[1] else 1
                positive = bool(re.search(r"k(?:>0|大于0|为正|是正数)", clause))
                negative = bool(re.search(r"k(?:<0|小于0|为负|是负数)", clause))
                lines = equations(clause) or equations(context)
                if positive and negative:
                    actual = None
                elif positive != negative:
                    actual = direction * (1 if positive else -1)
                elif len(lines) == 1 and _sign(number(lines[0][0])) == direction:
                    # Moving away from zero is certain; moving towards it could
                    # cross zero, so an initial value alone is insufficient.
                    actual = 1
                else:
                    actual = None
                claims.append(("k:steepness", None if actual is None else _matches_change(actual, relation)))

        lines = equations(clause) or equations(context)
        if len(lines) == 2:
            for comparison in re.finditer(r"前者|第一条|后者|第二条", clause):
                relation = _relation(clause[comparison.end():])
                if relation:
                    selected = 0 if comparison[0] in {"前者", "第一条"} else 1
                    change = _sign(abs(number(lines[selected][0])) - abs(number(lines[1 - selected][0])))
                    claims.append(("linear:comparison", _matches_change(change, relation)))
    return SlopeAssessment(tuple(claims))
