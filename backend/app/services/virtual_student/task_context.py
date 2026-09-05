"""Recover the active mathematical task from persisted teacher turns."""
import re
from .linear_math import equations, rate_model


def active_task(history, current: str = '') -> str:
    for speaker, content in reversed([*history, ('teacher', current)]):
        if speaker != 'teacher':
            continue
        if equations(content):
            return content
        model = rate_model(content)
        if model:
            return f'{content}（费用 y 与数量 x 的关系：y={model[0]}x+{model[1]}）'
        if re.search(r"换(?:一?道)?题|新题|不讲函数|不讨论数学", content):
            return ''
    return ''
