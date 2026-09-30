"""Shared clause boundaries for linear claims and student evidence."""

import re


_CLAUSE_BOUNDARY = re.compile(
    r"[。；;]|(?:不过|但是|然而|可是|(?<!不)但)"
    r"|(?<=[，,])(?=b(?:越大|变大|增大|决定|影响|控制))"
)
_ATTRIBUTION = re.compile(r"(?:有同学|有人|有些同学).{0,6}(?:说|认为|觉得|问)")
_OWN_STANCE = re.compile(r"我(?:也)?(?:认为|觉得|同意)")


def split_linear_clauses(text: str) -> list[str]:
    """Keep a quoted claim separate from the speaker's own later stance.

    Punctuation is optional before a first-person stance after attribution.
    Ordinary phrases such as ``b 变大，我觉得直线更陡`` stay intact because
    there is no prior attribution to separate from.
    """
    normalized = re.sub(r"\s+", "", text.lower())
    clauses = []
    for segment in _CLAUSE_BOUNDARY.split(normalized):
        attribution = _ATTRIBUTION.search(segment)
        if attribution:
            own_stance = _OWN_STANCE.search(segment, attribution.end())
            if own_stance:
                clauses.extend((segment[:own_stance.start()], segment[own_stance.start():]))
                continue
        clauses.append(segment)
    return [clause for clause in clauses if clause]
