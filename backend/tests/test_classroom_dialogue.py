from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.teaching_behavior import TeachingActionType
from app.services.llm.base import LLMContext
from app.services.llm.mock import MockLLMClient
from app.services.teaching_behavior import TeachingBehaviorAnalyzer
from app.services.virtual_student import (
    ClassroomAct,
    TeachingBehavior,
    VirtualStudentEngine,
    analyze_classroom_dialogue,
    detect_teacher_behavior,
)
from validation.case_loader import load_student_profile


CLASSROOM_CASES = (
    ("同学你好。", ClassroomAct.GREETING, TeachingActionType.CLASSROOM_INTERACTION),
    ("我们开始上课。", ClassroomAct.GREETING, TeachingActionType.CLASSROOM_INTERACTION),
    ("准备好了吗？", ClassroomAct.GREETING, TeachingActionType.CLASSROOM_INTERACTION),
    ("今天继续学习。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("先回顾一下昨天的内容。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("请看黑板。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("先写在草稿纸上。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("给你一分钟想一想。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("先别急着回答。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("请坐。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("注意听。", ClassroomAct.ORGANIZATION, TeachingActionType.CLASSROOM_INTERACTION),
    ("别紧张，大胆说。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("没关系，慢慢想。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("再试一次。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("已经很接近答案了。", ClassroomAct.ENCOURAGEMENT, TeachingActionType.FEEDBACK),
    ("差一点，再想想。", ClassroomAct.CORRECTIVE_FEEDBACK, TeachingActionType.FEEDBACK),
    ("你回答得很好。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("你回答的很好。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("回答正确。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("你的第一步是对的。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("对，就是这个意思。", ClassroomAct.FEEDBACK, TeachingActionType.FEEDBACK),
    ("这里不太对。", ClassroomAct.CORRECTIVE_FEEDBACK, TeachingActionType.FEEDBACK),
    ("前面正确，后面再检查一下。", ClassroomAct.CORRECTIVE_FEEDBACK, TeachingActionType.FEEDBACK),
    ("再说一遍。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("说完整一点。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("能说清楚一点吗？", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("请把理由补充完整。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("结合图像再说说。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("用自己的话讲一遍。", ClassroomAct.ELABORATION_REQUEST, TeachingActionType.QUESTION),
    ("我们继续。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("接着看下一题。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("回到刚才的问题。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("现在换一道题。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("今天先到这里。", ClassroomAct.CLOSURE, TeachingActionType.CLASSROOM_INTERACTION),
    ("下课。", ClassroomAct.CLOSURE, TeachingActionType.CLASSROOM_INTERACTION),
    ("课后再练习。", ClassroomAct.CLOSURE, TeachingActionType.CLASSROOM_INTERACTION),
    ("嗯。", ClassroomAct.ACKNOWLEDGEMENT, TeachingActionType.CLASSROOM_INTERACTION),
    ("好的。", ClassroomAct.ACKNOWLEDGEMENT, TeachingActionType.CLASSROOM_INTERACTION),
    ("可以。", ClassroomAct.ACKNOWLEDGEMENT, TeachingActionType.CLASSROOM_INTERACTION),
    ("继续。", ClassroomAct.TRANSITION, TeachingActionType.CLASSROOM_INTERACTION),
    ("然后呢？", ClassroomAct.CONTINUATION, TeachingActionType.CLASSROOM_INTERACTION),
)


EXTENDED_CLASSROOM_UTTERANCES = (
    # Greeting and opening (8)
    "大家好。", "早上好。", "上课吧。", "我们开始上课吧。", "可以开始了吗？",
    "准备开始。", "同学们好。", "现在开始上课。",
    # Positive feedback (12)
    "很好。", "非常好。", "真棒。", "不错。", "答得不错。", "说得很好。",
    "没错。", "完全正确。", "你答对了。", "你的思路对。", "这个方法正确。", "这一步没问题。",
    # Encouragement (10)
    "别着急。", "不要怕错。", "慢慢来。", "大胆说出来。", "试试看。",
    "你可以的。", "再努力一下。", "继续思考。", "加油。", "再想一想。",
    # Classroom organization (12)
    "看这里。", "翻到第十二页。", "拿出练习本。", "给你两分钟。", "声音大一点。",
    "认真观察。", "安静一下。", "停一下。", "打开课本。", "打开窗户。", "请关门。", "去办公室找老师。",
    # Transitions (10)
    "继续刚才的问题。", "下一问。", "往下看。", "换个例子。", "上一个问题。",
    "下面来看。", "进入下一步。", "这个先放一放。", "我们后面讨论。", "请继续。",
    # Closure (8)
    "这节课结束。", "今天到这里。", "下次再讲。", "课后完成练习。",
    "休息一下。", "老师再见。", "下课吧。", "今天的课结束了。",
    # Requests to elaborate (10)
    "重新讲一遍。", "展开说一说。", "具体说说。", "为什么这么想？", "依据是什么？",
    "还有吗？", "请接着说。", "刚才那句话是什么意思？", "说清楚一点。", "继续说理由。",
    # Understanding checks (8)
    "听懂了吗？", "有没有听懂？", "理解了吗？", "学会了吗？",
    "会了吗？", "清楚了吗？", "跟上了吗？", "能不能复述一下？",
    # Corrective feedback (7)
    "不太对。", "这一步错了。", "你再看看。", "这里有问题。",
    "这个判断有偏差。", "不是这样。", "你确定吗？",
)


SEMANTIC_NEIGHBOR_CASES = (
    *((text, ClassroomAct.GREETING) for text in (
        "同学们早。", "我们上课。", "准备上课了吗？", "现在可以上课了吧？", "咱们开始吧。",
    )),
    *((text, ClassroomAct.FEEDBACK) for text in (
        "干得漂亮。", "讲得真清楚。", "回答很到位。", "正是这个结论。",
        "这个思路没问题。", "这次答得可以。",
    )),
    *((text, ClassroomAct.ENCOURAGEMENT) for text in (
        "不用慌。", "想好了再说。", "再琢磨一下。", "别怕说错。", "你再尝试一下。", "先稳一稳。",
    )),
    *((text, ClassroomAct.ORGANIZATION) for text in (
        "把书翻开。", "看一下屏幕。", "请保持安静。", "请把笔拿出来。",
        "在本子上记一下。", "把练习册拿出来。",
    )),
    *((text, ClassroomAct.TRANSITION) for text in (
        "咱们接着来。", "看后面一道。", "接着刚才的内容。", "转到下一个问题。",
        "这个暂时跳过。", "我们往后继续。",
    )),
    *((text, ClassroomAct.CLOSURE) for text in (
        "今天就讲到这儿。", "这堂课结束。", "咱们下次接着讲。", "先休息一会儿。", "今天就先这样。",
    )),
    *((text, ClassroomAct.ELABORATION_REQUEST) for text in (
        "能再详细点吗？", "多说一点。", "把过程讲一下。", "你的理由呢？",
        "具体是怎么想的？", "再展开一点。",
    )),
    *((text, ClassroomAct.UNDERSTANDING_CHECK) for text in (
        "都听明白没有？", "现在会做了吗？", "能跟得上吗？", "你理解到哪里了？",
        "是否清楚？", "能再做一个吗？",
    )),
    *((text, ClassroomAct.CORRECTIVE_FEEDBACK) for text in (
        "好像不对。", "再核对一遍。", "这个地方需要改。", "前一步没问题，后一步有错。",
        "想法有点偏。", "这里得改一下。",
    )),
    *((text, ClassroomAct.ACKNOWLEDGEMENT) for text in (
        "好的呢。", "嗯嗯。", "行吧。", "明白。", "收到。",
    )),
    *((text, ClassroomAct.CONTEXTUAL_REFERENCE) for text in (
        "那又怎么样？", "前一个呢？", "这个怎么理解？", "刚刚那个怎么说？", "接下来怎么办？",
    )),
)


TRUE_OFF_TOPIC_CONTROLS = (
    "今天天气怎么样？", "你喜欢篮球吗？", "给我讲个笑话。", "中午吃什么？",
    "最近有什么电影？", "周末去哪里玩？", "你会打游戏吗？", "这首歌是谁唱的？",
    "手机多少钱？", "你昨晚睡得好吗？", "今天几号？", "北京有什么景点？",
    "新闻里发生了什么？", "你喜欢小猫吗？", "帮我买一杯奶茶。", "你家住在哪里？",
    "哪个球队赢了？", "讲个故事吧。", "你会做饭吗？", "暑假有什么计划？",
)


@pytest.mark.parametrize(("teacher_text", "expected_act"), SEMANTIC_NEIGHBOR_CASES)
def test_unseen_semantic_neighbors_use_compositional_classification(
    teacher_text: str,
    expected_act: ClassroomAct,
) -> None:
    intent = analyze_classroom_dialogue(teacher_text)
    report = TeachingBehaviorAnalyzer().analyze(teacher_text)
    response = MockLLMClient().respond(teacher_text, LLMContext())

    assert intent.primary_act is expected_act
    assert intent.off_topic is False
    assert report.action_type is not TeachingActionType.OFF_TOPIC
    assert "无关" not in response
    assert "不是这节课" not in response


@pytest.mark.parametrize("teacher_text", TRUE_OFF_TOPIC_CONTROLS)
def test_high_threshold_off_topic_still_rejects_clear_topic_drift(
    teacher_text: str,
) -> None:
    intent = analyze_classroom_dialogue(teacher_text)
    report = TeachingBehaviorAnalyzer().analyze(teacher_text)

    assert intent.primary_act is ClassroomAct.OFF_TOPIC
    assert intent.classification_source == "off_topic_signal"
    assert report.action_type is TeachingActionType.OFF_TOPIC


def test_ambiguous_unseen_turn_defaults_to_neutral_classroom_interaction() -> None:
    intent = analyze_classroom_dialogue(
        "请处理一下。",
        conversation_history=(("teacher", "我们比较两条直线。"),),
    )

    assert intent.primary_act is ClassroomAct.ACKNOWLEDGEMENT
    assert intent.classification_source == "classroom_context_fallback"
    assert intent.confidence < 0.5


@pytest.mark.parametrize(
    "teacher_text",
    ("给我讲讲量子物理。", "你喜欢喝茶吗？", "介绍一下古代建筑。"),
)
def test_unseen_non_classroom_domains_are_rejected_without_domain_whitelist(
    teacher_text: str,
) -> None:
    intent = analyze_classroom_dialogue(teacher_text)

    assert intent.primary_act is ClassroomAct.OFF_TOPIC
    assert intent.classification_source == "open_set_rejection"


def test_teaching_reference_overrides_a_surface_off_topic_word() -> None:
    intent = analyze_classroom_dialogue("这道篮球应用题有几种解法？")

    assert intent.off_topic is False
    assert intent.has(ClassroomAct.SUBJECT_CONTENT)


@pytest.mark.parametrize(
    ("teacher_text", "expected_act"),
    (
        ("你的解答说得相当精彩。", ClassroomAct.FEEDBACK),
        ("别灰心，再来一次。", ClassroomAct.ENCOURAGEMENT),
        ("请把教材摊开放好。", ClassroomAct.ORGANIZATION),
        ("请进一步详细阐述你的依据。", ClassroomAct.ELABORATION_REQUEST),
        ("是否已经掌握？", ClassroomAct.UNDERSTANDING_CHECK),
    ),
)
def test_compositional_features_generalize_beyond_seed_wording(
    teacher_text: str,
    expected_act: ClassroomAct,
) -> None:
    intent = analyze_classroom_dialogue(teacher_text)

    assert intent.primary_act is expected_act
    assert intent.classification_source in {"semantic", "rules+semantic"}


@pytest.mark.parametrize("teacher_text", EXTENDED_CLASSROOM_UTTERANCES)
def test_extended_classroom_utterances_are_not_misclassified_as_off_topic(
    teacher_text: str,
) -> None:
    classroom = analyze_classroom_dialogue(teacher_text)
    report = TeachingBehaviorAnalyzer().analyze(teacher_text)
    response = MockLLMClient().respond(teacher_text, LLMContext())

    assert len(EXTENDED_CLASSROOM_UTTERANCES) == 85
    assert classroom.off_topic is False
    assert report.action_type is not TeachingActionType.OFF_TOPIC
    assert report.concept != "非教学话题"
    assert "无关" not in response
    assert "不是这节课" not in response


@pytest.mark.parametrize(("teacher_text", "expected_act", "expected_action"), CLASSROOM_CASES)
def test_classroom_short_dialogue_is_not_off_topic_and_has_consistent_behavior(
    teacher_text: str,
    expected_act: ClassroomAct,
    expected_action: TeachingActionType,
) -> None:
    classroom = analyze_classroom_dialogue(teacher_text)
    report_behavior = TeachingBehaviorAnalyzer().analyze(teacher_text)
    state_behavior = detect_teacher_behavior(teacher_text)

    assert classroom.act is expected_act
    assert classroom.off_topic is False
    assert report_behavior.action_type is expected_action
    if expected_act is ClassroomAct.ELABORATION_REQUEST:
        assert state_behavior is TeachingBehavior.EFFECTIVE_QUESTION
    else:
        assert state_behavior is TeachingBehavior.NEUTRAL

    response = MockLLMClient().respond(
        teacher_text,
        LLMContext(
            student_profile_id="student_a",
            misconception_status="active",
            conversation_history=(
                ("teacher", "比较两条直线后，你发现什么？"),
                ("student", "我觉得 b 越大直线越陡。"),
            ),
        ),
    )
    assert response.strip()
    assert "无关" not in response
    assert "不是这节课" not in response


@pytest.mark.parametrize("teacher_text", ("今天天气怎么样？", "你喜欢篮球吗？", "给我讲个笑话。"))
def test_genuine_off_topic_dialogue_is_still_redirected(teacher_text: str) -> None:
    classroom = analyze_classroom_dialogue(teacher_text)
    report = TeachingBehaviorAnalyzer().analyze(teacher_text)
    response = MockLLMClient().respond(teacher_text, LLMContext())

    assert classroom.off_topic is True
    assert report.action_type is TeachingActionType.OFF_TOPIC
    assert report.concept == "非教学话题"
    assert "无关" in response or "不是这节课" in response
    assert detect_teacher_behavior(teacher_text) is TeachingBehavior.NEUTRAL


@pytest.mark.parametrize(
    ("teacher_text", "expected_action", "expected_state_behavior"),
    (
        ("不错，但 b 不影响斜率，只改变截距。", TeachingActionType.CORRECTION, TeachingBehavior.TARGETED_CORRECTION),
        ("很好，再解释一下为什么。", TeachingActionType.QUESTION, TeachingBehavior.EFFECTIVE_QUESTION),
        ("没关系，我们比较 y=2x+1 和 y=2x+3。", TeachingActionType.EXAMPLE, TeachingBehavior.EFFECTIVE_EXAMPLE),
        ("答案是 5，你记住了吗？", TeachingActionType.DIRECT_ANSWER, TeachingBehavior.DIRECT_ANSWER),
        ("正确答案为 5。", TeachingActionType.DIRECT_ANSWER, TeachingBehavior.DIRECT_ANSWER),
        ("直接写 5。", TeachingActionType.DIRECT_ANSWER, TeachingBehavior.DIRECT_ANSWER),
    ),
)
def test_compound_and_numeric_instruction_keeps_the_instructional_act(
    teacher_text: str,
    expected_action: TeachingActionType,
    expected_state_behavior: TeachingBehavior,
) -> None:
    intent = analyze_classroom_dialogue(teacher_text)
    report = TeachingBehaviorAnalyzer().analyze(teacher_text)
    response = MockLLMClient().respond(
        teacher_text,
        LLMContext(student_profile_id="student_a", misconception_status="active"),
    )

    assert intent.off_topic is False
    assert report.action_type is expected_action
    assert detect_teacher_behavior(teacher_text) is expected_state_behavior
    assert "无关" not in response
    assert "不是这节课" not in response
    if expected_action in {TeachingActionType.CORRECTION, TeachingActionType.QUESTION, TeachingActionType.EXAMPLE}:
        assert not response.startswith("谢谢老师")


@pytest.mark.parametrize(
    "teacher_text",
    ("请看黑板上的函数图像。", "下面来看一次函数图像。", "先把公式写在草稿纸上。"),
)
def test_classroom_management_with_subject_terms_is_not_treated_as_explanation(
    teacher_text: str,
) -> None:
    intent = analyze_classroom_dialogue(teacher_text)
    report = TeachingBehaviorAnalyzer().analyze(teacher_text)
    response = MockLLMClient().respond(teacher_text, LLMContext())

    assert intent.has_subject_content is True
    assert intent.primary_act in {ClassroomAct.ORGANIZATION, ClassroomAct.TRANSITION}
    assert report.action_type is TeachingActionType.CLASSROOM_INTERACTION
    assert response.startswith(("好", "好的"))


@pytest.mark.parametrize(
    "teacher_text",
    (
        "你回答得很好。",
        "没关系，慢慢想。",
        "请看黑板。",
        "我们继续。",
        "今天先到这里。",
    ),
)
def test_non_content_classroom_interaction_does_not_change_cognitive_state(
    teacher_text: str,
) -> None:
    engine = VirtualStudentEngine(load_student_profile("student_a"))
    before = engine.snapshot()
    opportunity = engine.get_correction_opportunity(teacher_text)

    engine.update_from_teacher_text(teacher_text)
    response = MockLLMClient().respond(
        teacher_text,
        LLMContext(student_profile_id="student_a", misconception_status="active"),
    )
    evidence = engine.apply_student_response_evidence(response, teacher_text, opportunity)

    assert engine.snapshot() == before
    assert evidence.evidence_insufficient is True


def test_affirmation_is_feedback_but_explicit_answer_is_direct_answer() -> None:
    analyzer = TeachingBehaviorAnalyzer()

    affirmation = analyzer.analyze("对，就是这样。")
    answer = analyzer.analyze("答案是：b 只影响截距，记住。")

    assert affirmation.action_type is TeachingActionType.FEEDBACK
    assert affirmation.gave_answer_directly is False
    assert detect_teacher_behavior("对，就是这样。") is TeachingBehavior.NEUTRAL
    assert answer.action_type is TeachingActionType.DIRECT_ANSWER
    assert answer.gave_answer_directly is True


def test_session_records_classroom_interactions_without_changing_cognition(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    with TestClient(app) as client:
        scenario = client.get("/api/scenarios").json()[0]
        student = client.get("/api/virtual-students").json()[0]
        created = client.post(
            "/api/sessions",
            json={"scenario_id": scenario["id"], "virtual_student_id": student["id"]},
        )
        if created.json()["dialogue_records"]:
            client.post(f"/api/sessions/{created.json()['id']}/end")
            created = client.post(
                "/api/sessions",
                json={"scenario_id": scenario["id"], "virtual_student_id": student["id"]},
            )

        session_id = created.json()["id"]
        initial_trace = created.json()["cognitive_trace"]
        praised = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "你回答得很好。"},
        )
        organized = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "请看黑板。"},
        )
        off_topic = client.post(
            f"/api/sessions/{session_id}/messages",
            json={"teacher_text": "你喜欢篮球吗？"},
        )
        client.post(f"/api/sessions/{session_id}/end")

    assert praised.status_code == 200
    assert praised.json()["behavior_records"][-1]["action_type"] == "feedback"
    assert praised.json()["behavior_summary"]["feedback_count"] == 1
    assert "无关" not in praised.json()["dialogue_records"][-1]["content"]

    organized_data = organized.json()
    assert organized_data["behavior_records"][-1]["action_type"] == "classroom_interaction"
    assert organized_data["behavior_summary"]["classroom_interaction_count"] == 1

    data = off_topic.json()
    assert data["behavior_records"][-1]["action_type"] == "off_topic"
    assert data["behavior_summary"]["classroom_interaction_count"] == 1
    assert data["behavior_summary"]["off_topic_count"] == 1
    assert data["cognitive_trace"]["current_state"] == initial_trace["current_state"]
    assert data["cognitive_trace"]["current_misconception"] == initial_trace["current_misconception"]
