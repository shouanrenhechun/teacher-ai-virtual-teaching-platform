import pytest

from app.services.llm.base import LLMContext
from app.services.llm.mock import MockLLMClient
from app.services.teaching_behavior import TeachingBehaviorAnalyzer
from app.services.virtual_student import VirtualStudentEngine
from app.services.virtual_student.behavior import detect_teacher_behavior, TeachingBehavior
from app.services.virtual_student.linear_math import equations
from app.services.virtual_student.task_context import active_task
from validation.case_loader import load_student_profile


@pytest.mark.parametrize('left,right', [('2', '2.0'), ('0.5', '1/2'), ('0', '-0'), ('-3', '3'), ('-2.50', '2.5')])
@pytest.mark.parametrize('student', ['student_a', 'student_b', 'student_c'])
def test_equal_magnitude_slopes_are_never_ranked(left, right, student):
    reply = MockLLMClient().respond(f'比较 y={left}x+1 和 y={right}x+3，哪条更陡？', LLMContext(student_profile_id=student))
    assert '一样陡' in reply
    assert '更大' not in reply


def test_equation_values_are_normalized_without_evaluating_code():
    assert equations('y=x+3，y=-x-1，y=0.50x+2') == (('1', '3'), ('-1', '-1'), ('1/2', '2'))
    assert equations('y=1/0x+2') == ()


@pytest.mark.parametrize('text', ['有同学说“b越大直线越陡”，你同意吗？', 'b越大直线越陡，这个说法正确吗？'])
def test_questioning_an_error_is_not_incorrect_instruction(text):
    assert detect_teacher_behavior(text) is TeachingBehavior.EFFECTIVE_QUESTION
    engine = VirtualStudentEngine(load_student_profile('student_a'))
    before = engine.classroom_state.understanding
    engine.update_from_teacher_text(text)
    assert engine.classroom_state.understanding == before
    report = TeachingBehaviorAnalyzer().analyze(text, llm_client=MockLLMClient())
    assert report.concept == '未判定知识'


@pytest.mark.parametrize('text', ['我们不能说 b越大直线越陡，这个说法不正确。', '很好，但 b 表示斜率这个结论需要改。'])
def test_denied_error_is_a_correction_in_both_paths(text):
    assert detect_teacher_behavior(text) is TeachingBehavior.TARGETED_CORRECTION
    report = TeachingBehaviorAnalyzer().analyze(text, llm_client=MockLLMClient())
    assert report.action_type.value == 'correction'
    assert report.knowledge_accuracy >= 0.9


@pytest.mark.parametrize('text', ['记住，k 决定截距，b 决定斜率。', '因为 b 控制倾斜程度，所以增大 b 会使直线更陡。'])
def test_wrong_claim_cannot_receive_mock_default_high_score(text):
    report = TeachingBehaviorAnalyzer().analyze(text, llm_client=MockLLMClient())
    assert report.knowledge_accuracy <= 0.2
    assert detect_teacher_behavior(text) is TeachingBehavior.INCORRECT_EXPLANATION


@pytest.mark.parametrize('count', [0, 1, 3, 6])
def test_social_turns_preserve_task(count):
    history = [('teacher', '看 y=2x+1 和 y=2x+3。')]
    history.extend([('teacher', '说得不错。'), ('student', '谢谢老师。')] * count)
    context = LLMContext(conversation_history=tuple(history[-8:]), task_context=active_task(history))
    reply = MockLLMClient().respond('那它们与纵轴相交的位置呢？', context)
    assert '1、3' in reply
    reply = MockLLMClient().respond('先把横坐标取成零，再分别算一下。', context)
    assert '1、3' in reply


def test_new_task_replaces_old_and_elliptical_input_is_carried_forward():
    history = (('teacher', '当 y=2x+3，x=0 时，y 是多少？'),)
    assert '3' in MockLLMClient().respond('如果 y=-2x+3 呢？', LLMContext(conversation_history=history))
    assert active_task(history, '换一道题，先读题。') == ''
    assert active_task(history, '现在 y=4x-8。') == '现在 y=4x-8。'


@pytest.mark.parametrize('text', ['先别急着作答，留半分钟在心里组织一下。', '你现在不用再计算，先听我讲。', '我相信你可以独立判断。', '你能完成，不着急。'])
def test_blocked_tasks_and_ability_statements_are_not_questions(text):
    report = TeachingBehaviorAnalyzer().analyze(text, llm_client=MockLLMClient())
    assert report.action_type.value in {'classroom_interaction', 'feedback'}
    assert report.knowledge_accuracy == 0
    assert detect_teacher_behavior(text) is TeachingBehavior.NEUTRAL


def test_method_change_is_not_lost_behind_praise():
    text = '你刚才做得很好，现在换个办法试一下。'
    assert TeachingBehaviorAnalyzer().analyze(text).action_type.value == 'question'
    assert '谢谢' not in MockLLMClient().respond(text)


def test_repeat_evidence_stays_deduplicated_after_restore():
    profile = load_student_profile('student_a')
    engine = VirtualStudentEngine(profile)
    text = '请比较 y=2x+1 和 y=2x+3。'
    reply = MockLLMClient().respond(text)
    def turn(engine, text):
        opportunity = engine.get_correction_opportunity(text)
        engine.update_from_teacher_text(text)
        engine.apply_student_response_evidence(reply, text, opportunity)
    turn(engine, text)
    first = engine.snapshot()
    engine = VirtualStudentEngine.from_exported_state(profile, engine.export_state())
    for _ in range(4):
        turn(engine, '比较 y=2.0x+1 和 y=2x+3。')
    assert engine.classroom_state.understanding == first.classroom_state.understanding
    assert engine.snapshot().knowledge_states == first.knowledge_states
    assert engine.snapshot().misconceptions == first.misconceptions


@pytest.mark.parametrize('base,rate,expected', [('八', '两', 'y=2x+8'), ('十二', '三', 'y=3x+12'), ('5', '1.5', 'y=3/2x+5')])
def test_fixed_and_per_unit_costs_form_a_model(base, rate, expected):
    text = f'固定费用{base}元，每件再收{rate}元，你能把数量和费用联系起来吗？'
    assert expected in MockLLMClient().respond(text)


def test_life_context_intercept_followup():
    history = (('teacher', '把费用记为 y，路程记为 x，可以写成 y=2x+8。'),)
    reply = MockLLMClient().respond('这里的八元对应图像的哪个特征？', LLMContext(conversation_history=history))
    assert '截距' in reply and '8' in reply


@pytest.mark.parametrize('text', ['k 决定截距，听懂了吗？', 'k 决定截距，但 b 决定斜率这个说法不正确。'])
def test_later_question_or_denial_does_not_erase_an_asserted_error(text):
    assert TeachingBehaviorAnalyzer().analyze(text, llm_client=MockLLMClient()).knowledge_accuracy <= 0.2
