"""Bounded claim checking; unknown propositions are deliberately unscored."""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ClaimAssessment:
    correct: bool | None = None
    error_stance: str | None = None  # asserted, denied, questioned


def assess_claims(text: str) -> ClaimAssessment:
    text = re.sub(r"\s+", "", text.lower())
    results = []
    stances = []
    for sentence in re.split(r"[。；;]", text):
        patterns = (
            (r"b(?:只)?(?:决定|表示|控制|影响|管|是)(?:直线的)?(?:斜率|倾斜程度)", False),
            (r"k(?:只)?(?:决定|表示|控制|影响|管|是)(?:直线的)?(?:截距|上下位置)", False),
            (r"b[^，,]{0,12}(?:越大|变大|增大)[^，,]{0,12}(?:更陡|越陡|变陡)", False),
            (r"b(?:只)?(?:影响|决定|表示|控制|管|是)(?:直线的)?(?:截距|上下位置|位置)", True),
            (r"k(?:只)?(?:影响|决定|表示|控制|管|是)(?:直线的)?(?:斜率|倾斜程度|倾斜)", True),
            (r"b不(?:影响|改变)斜率", True),
            (r"(?:平方就是分别平方|没有中间项|不需要中间项)", False),
        )
        for pattern, truth in patterns:
            for match in re.finditer(pattern, sentence):
                start = max(sentence.rfind('，', 0, match.start()), sentence.rfind(',', 0, match.start())) + 1
                end_match = re.search(r'[，,]', sentence[match.end():])
                end = match.end() + end_match.start() if end_match else len(sentence)
                clause = sentence[start:end]
                following = re.split(r'[，,]', sentence[end + 1:])[0]
                question = bool(re.search(r'[?？]|是否|对不对|正确吗|为什么', clause)) or bool(
                    re.match(r'(?:你)?(?:同意|觉得|认为).*[?？吗]', following)
                ) or bool(
                    re.match(r'(?:这个|该)(?:说法|结论|观点).*(?:正确吗|对不对|成立吗)', following)
                )
                denial_text = clause + (following if re.match(r'(?:这个|该)(?:说法|结论|观点)', following) else '')
                denied = bool(re.search(r'不能说|不(?:能)?认为|不正确|不对|需要改|推翻|错误', denial_text))
                # Attribution without endorsement is a question for discussion.
                quoted = bool(re.search(r"(?:有同学|有人).{0,4}说", sentence[:match.start()]))
                local_denial = (denied and not truth) or bool(re.search(r"(?:不是|并非|不要说)$", sentence[:match.start()]))
                if question or quoted:
                    if not truth:
                        stances.append('questioned')
                    continue
                results.append(not truth if local_denial else truth)
                if not truth:
                    stances.append('denied' if local_denial else 'asserted')
    correct = all(results) if results else None
    stance = next((s for s in ('asserted', 'denied', 'questioned') if s in stances), None)
    return ClaimAssessment(correct, stance)
