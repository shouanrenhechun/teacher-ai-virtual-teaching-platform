"""Recover the active mathematical task from persisted teacher turns."""
import re
from .linear_math import equations, rate_model


def active_task(history, current: str = '') -> str:
    from .binomial_plan import binomials
    for speaker, content in reversed([*history, ('teacher', current)]):
        if speaker != 'teacher':
            continue
        content = re.split(r'口误[，,:：]?|更正为[：:]?|改成[：:]?\s*(?=y=|\()|应该是[：:]?', content)[-1]
        if binomials(content):
            return content
        if equations(content):
            return content
        model = rate_model(content)
        if model:
            return f'{content}（费用 y 与数量 x 的关系：y={model[0]}x+{model[1]}）'
        if re.search(r"换(?:一?道)?题|新题|不讲函数|不讨论数学", content):
            return ''
    return ''


def task_identity(text: str, context: str = '') -> str:
    from .binomial_plan import binomials
    source = text or context
    facts = equations(source) or equations(context)
    squares = binomials(source) or binomials(context)
    if facts:
        return 'linear:' + repr(sorted(set(facts)))
    if squares:
        return 'square:' + repr(sorted(set(squares)))
    if any(word in source for word in ('平方', '中间项', 'ab')):
        return 'concept:binomial_square'
    if any(word in source.lower() for word in ('斜率', '截距', '图像', '倾斜', 'k', 'b')):
        return 'concept:linear_kb'
    return ''
