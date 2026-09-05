import pytest

from app.services.llm.base import LLMContext
from app.services.llm.mock import MockLLMClient
from app.services.teaching_behavior import TeachingBehaviorAnalyzer
from app.services.virtual_student import VirtualStudentEngine
from app.services.virtual_student.classroom_intent import ClassroomAct, analyze_classroom_dialogue
from validation.case_loader import load_student_profile


@pytest.mark.parametrize("preface", ("加油", "很好", "我相信你能够独立完成"))
@pytest.mark.parametrize("question", ("你觉得 k 变大时图像会怎样？", "如果固定 k，只改变 b，图像会怎样？"))
def test_affective_preface_preserves_task_and_state(preface, question):
    client = MockLLMClient()
    context = LLMContext()
    compound = preface + "，" + question
    assert client.respond(compound, context) == client.respond(question, context)
    analyzer = TeachingBehaviorAnalyzer()
    report = analyzer.analyze(compound, llm_client=client)
    assert report.action_type.value == "guided_question"
    assert not report.gave_answer_directly
    plain_engine = VirtualStudentEngine(load_student_profile("student_a"))
    compound_engine = VirtualStudentEngine(load_student_profile("student_a"))
    plain_engine.update_from_teacher_text(question)
    compound_engine.update_from_teacher_text(compound)
    assert compound_engine.snapshot() == plain_engine.snapshot()
    assert compound_engine.classroom_state.understanding == 0.68


@pytest.mark.parametrize("text", ("不要再想了，直接告诉我。", "请直接告诉我结果。", "答案是什么？"))
def test_request_does_not_supply_an_answer(text):
    intent = analyze_classroom_dialogue(text)
    assert not intent.has(ClassroomAct.DIRECT_ANSWER)
    report = TeachingBehaviorAnalyzer().analyze(text, llm_client=MockLLMClient())
    assert not report.gave_answer_directly
    assert report.action_type.value != "direct_answer"
    engine = VirtualStudentEngine(load_student_profile("student_a"))
    before = engine.classroom_state.surface_recall
    engine.update_from_teacher_text(text)
    assert engine.classroom_state.surface_recall == before
    assert "记下这个答案" not in MockLLMClient().respond(text)


@pytest.mark.parametrize("text", ("我相信你能够独立完成。", "老师相信你能做到。"))
def test_belief_in_student_is_encouragement(text):
    intent = analyze_classroom_dialogue(text)
    assert intent.has(ClassroomAct.ENCOURAGEMENT)
    assert "试" in MockLLMClient().respond(text) or "想" in MockLLMClient().respond(text)


@pytest.mark.parametrize("text", ("你说得并不正确。", "你的解答不正确。", "你的方法不对。"))
def test_negated_evaluation_is_not_praise(text):
    intent = analyze_classroom_dialogue(text)
    assert intent.has(ClassroomAct.CORRECTIVE_FEEDBACK)
    assert not intent.has(ClassroomAct.FEEDBACK)
    assert "谢谢" not in MockLLMClient().respond(text)


def test_polarity_does_not_cross_clause_boundaries():
    intent = analyze_classroom_dialogue("你的方法正确，但你说得不清楚。")
    assert intent.has(ClassroomAct.FEEDBACK)
    assert intent.has(ClassroomAct.CORRECTIVE_FEEDBACK)


def test_procedural_question_uses_available_context_without_inventing_results():
    text = "先取两个不同的数代进去，你发现了什么？"
    intent = analyze_classroom_dialogue(text)
    assert intent.primary_act is ClassroomAct.GUIDED_QUESTION
    assert TeachingBehaviorAnalyzer().analyze(text).action_type.value == "guided_question"
    client = MockLLMClient()
    assert "条件" in client.respond(text)
    context = LLMContext(conversation_history=(("teacher", "比较 y=2x+1 和 y=2x+3。"),))
    assert "一样陡" in client.respond(text, context)
