"""Exact binomial facts and state-aware response plans, shared by both providers."""
import re

from .linear_math import NUMBER, number, display
from .response_plan import StudentResponsePlan
from .classroom_intent import analyze_classroom_dialogue, ClassroomAct


def binomials(text: str):
    compact = re.sub(r"\s+", "", text).replace("²", "^2").replace("（", "(").replace("）", ")")
    result = []
    for match in re.finditer(rf"\(({NUMBER}|[+-]?)x({NUMBER})\)\^2", compact):
        try:
            k = number({'': '1', '+': '1', '-': '-1'}.get(match[1], match[1]))
            b = number(match[2])
        except (ValueError, ZeroDivisionError):
            continue
        result.append((display(k), display(b)))
    return tuple(result)


def polynomial(k: str, b: str, *, omit_middle=False):
    a, c = number(k), number(b)
    terms = [(a*a, 'x²'), (0 if omit_middle else 2*a*c, 'x'), (c*c, '')]
    result = ''
    for value, variable in terms:
        if not value:
            continue
        magnitude = '' if abs(value) == 1 and variable else display(abs(value))
        result += ('-' if value < 0 else '+' if result else '') + magnitude + variable
    return result or '0'


def build_binomial_plan(text, context):
    from .task_context import active_task
    task = active_task(context.conversation_history, text) or context.task_context
    expressions = binomials(text) or binomials(task)
    act = analyze_classroom_dialogue(text, conversation_history=context.conversation_history)
    shape = 'binomial_explain'
    from .propositions import assess_claims
    if assess_claims(text).error_stance == 'asserted':
        shape = 'binomial_misconception'
    elif act.primary_act is ClassroomAct.OFF_TOPIC:
        shape = 'off_topic'
    elif act.primary_act is ClassroomAct.FEEDBACK and not act.has_subject_content:
        shape = 'praise'
    elif act.primary_act in {ClassroomAct.GREETING, ClassroomAct.ORGANIZATION, ClassroomAct.TRANSITION, ClassroomAct.CLOSURE, ClassroomAct.ENCOURAGEMENT, ClassroomAct.ACKNOWLEDGEMENT, ClassroomAct.CONTINUATION} and not act.has_subject_content:
        shape = 'classroom_ack'
    elif act.has(ClassroomAct.UNDERSTANDING_CHECK):
        shape = 'binomial_understanding'
    elif act.has(ClassroomAct.DIRECT_ANSWER) or re.search(r'(?:答案|结论|结果)(?:是|为)|记住|记下', text):
        shape = 'binomial_recall'
    elif expressions and not any(word in text for word in ('为什么', '中间项', '交叉', '两个相同', '相乘')):
        shape = 'binomial_calculate'
    elif not expressions and not any(word in text for word in ('平方', '展开', '中间项', '交叉', 'ab', '为什么', '依据', '理由', '相乘')):
        shape = 'clarify'
    facts = {'binomials': expressions, 'fee_context': False, 'symbolic_sign': -1 if '(a-b)' in re.sub(r'\s+', '', text + task) else 1}
    # Observation of multiplication is scaffolding; a bare formula request is not.
    facts['scaffolded'] = any(word in text for word in ('相乘', '交叉', '中间项', '两个相同'))
    return StudentResponsePlan(
        semantic_type='binomial_square', topic=context.topic, task_type='calculation' if expressions else 'explanation',
        task_context=task, teacher_text=text, response_goal='answer_question',
        misconception_status=context.misconception_status, misconception_strength=context.misconception_strength,
        current_belief_stance={'active': 'holds_misconception', 'weakening': 'conflicted', 'provisional': 'mostly_correct_but_unstable', 'corrected': 'stable_correct'}.get(context.misconception_status, 'unknown'),
        content_facts=facts, response_shape=shape, must_include=('cross_terms',) if shape == 'binomial_explain' else (),
        style_constraints={'response_style': context.response_style, 'confidence_style': context.confidence_style}, turn_index=context.turn_index,
    )


def render_binomial(plan):
    status = plan.misconception_status
    shape = plan.response_shape
    if shape == 'binomial_misconception' and status != 'corrected':
        return '我原来也觉得每一项分别平方就行，没有中间项，但还不太确定。'
    if shape == 'binomial_recall':
        return '我先记下这个公式，但还不太确定中间项为什么出现，需要自己展开才能确认。'
    if shape == 'binomial_understanding' and status != 'corrected':
        return '还没有完全听懂，我容易漏掉中间项，想把两个括号再乘一遍。'
    if shape == 'binomial_calculate':
        k, b = plan.content_facts['binomials'][0]
        if status == 'active':
            return f'我先算成 {polynomial(k, b, omit_middle=True)}，觉得每一项分别平方就行，但还不确定中间项。'
        middle = display(2 * number(k) * number(b))
        return f'展开得到 {polynomial(k, b)}，因为两个交叉项合起来是 {middle}x。'
    if 'ab' in plan.teacher_text.lower():
        if plan.content_facts['symbolic_sign'] == -1:
            return '两个交叉项分别是 -ab 和 -ab，合起来是 -2ab，所以 (a-b)^2=a²-2ab+b²。'
        return 'ab 和 ba 从两个交叉相乘中各出现一次，所以合起来是 2ab，中间项不能漏掉。'
    if plan.content_facts['binomials'] and (status != 'active' or plan.content_facts['scaffolded']):
        k, b = plan.content_facts['binomials'][0]
        return f'展开得到 {polynomial(k, b)}，因为两个交叉项合并成 {display(2 * number(k) * number(b))}x，中间项不能漏掉。'
    if status == 'active' and not plan.content_facts['scaffolded']:
        return '我记得每一项分别平方，但还不太确定交叉相乘要不要算进去。'
    return '把两个相同括号相乘，ab 和 ba 各出现一次，所以中间项是 2ab，不能漏掉。'
