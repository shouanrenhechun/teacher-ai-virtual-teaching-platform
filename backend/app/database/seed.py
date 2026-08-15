from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    KnowledgeState,
    Misconception,
    TrainingScenario,
    VirtualStudent,
)


TARGET_SCENARIO_TITLE = "一次函数：k 与 b 的意义"
LEGACY_SCENARIO_TITLE = "分数的意义：从部分到整体"


def _ensure_scenario(db: Session) -> TrainingScenario:
    scenario = db.scalar(
        select(TrainingScenario).where(TrainingScenario.title == TARGET_SCENARIO_TITLE)
    )
    if scenario is None:
        # Convert the module 1-only seed in place when upgrading an existing local DB.
        scenario = db.scalar(
            select(TrainingScenario).where(TrainingScenario.title == LEGACY_SCENARIO_TITLE)
        )
    if scenario is None:
        scenario = TrainingScenario(title=TARGET_SCENARIO_TITLE)
        db.add(scenario)

    scenario.title = TARGET_SCENARIO_TITLE
    scenario.subject = "初中数学"
    scenario.grade = "初二"
    scenario.topic = "一次函数"
    scenario.teaching_goal = "理解 y=kx+b 中 k 与 b 的意义，并能结合图像解释直线的变化。"
    scenario.description = (
        "围绕一次函数 y=kx+b 开展模拟教学，重点观察学生能否区分 k 对倾斜程度的影响，"
        "以及 b 对截距和平移位置的影响。"
    )
    return scenario


def _replace_student_states(
    db: Session,
    student: VirtualStudent,
    knowledge_states: list[KnowledgeState],
    misconceptions: list[Misconception],
) -> None:
    # Flush orphan deletes before inserting replacement rows because each
    # student/knowledge-point pair has a unique constraint.
    student.knowledge_states.clear()
    student.misconceptions.clear()
    db.flush()
    student.knowledge_states = knowledge_states
    student.misconceptions = misconceptions


def _ensure_student(
    db: Session,
    *,
    name: str,
    grade: str,
    base_level: float,
    personality_description: str,
    initiative: float,
    confidence: float,
    knowledge_states: list[KnowledgeState],
    misconceptions: list[Misconception],
) -> VirtualStudent:
    student = db.scalar(select(VirtualStudent).where(VirtualStudent.name == name))
    if student is None and name == "学生 A":
        # Convert the module 1-only seed in place when upgrading an existing local DB.
        student = db.scalar(select(VirtualStudent).where(VirtualStudent.name == "小雨"))
    if student is None:
        student = VirtualStudent(name=name)
        db.add(student)

    student.name = name
    student.grade = grade
    student.base_level = base_level
    student.personality_description = personality_description
    student.initiative = initiative
    student.confidence = confidence
    _replace_student_states(db, student, knowledge_states, misconceptions)
    return student


def seed_initial_data(db: Session) -> None:
    """Insert or upgrade the small, idempotent dataset for the MVP demo."""
    _ensure_scenario(db)

    _ensure_student(
        db,
        name="学生 A",
        grade="初二",
        base_level=0.68,
        personality_description="偏谨慎，不太主动提问，通常会先确认教师的提示再继续回答。",
        initiative=0.3,
        confidence=0.55,
        knowledge_states=[
            KnowledgeState(knowledge_point="一次函数基本定义", mastery=0.85),
            KnowledgeState(knowledge_point="一次函数基本计算", mastery=0.82),
            KnowledgeState(knowledge_point="一次函数图像基础", mastery=0.65),
            KnowledgeState(knowledge_point="k 对直线倾斜程度的影响", mastery=0.3),
            KnowledgeState(knowledge_point="b 对截距和平移位置的影响", mastery=0.25),
        ],
        misconceptions=[
            Misconception(
                name="b 越大，直线越陡",
                concept="k 与 b 的图像意义",
                description="把 b 的变化误认为会改变直线的倾斜程度，混淆 k 和 b 的作用。",
                strength=0.85,
                correction_condition="通过固定 k、改变 b 的图像对比，引导学生观察倾斜程度和截距分别如何变化。",
            )
        ],
    )
    _ensure_student(
        db,
        name="学生 B",
        grade="初二",
        base_level=0.62,
        personality_description="擅长代入和计算，习惯套用公式，但需要追问才能解释计算背后的图像意义。",
        initiative=0.45,
        confidence=0.6,
        knowledge_states=[
            KnowledgeState(knowledge_point="一次函数基本定义", mastery=0.7),
            KnowledgeState(knowledge_point="一次函数基本计算", mastery=0.92),
            KnowledgeState(knowledge_point="一次函数图像基础", mastery=0.35),
            KnowledgeState(knowledge_point="k 与 b 的意义解释", mastery=0.28),
        ],
        misconceptions=[
            Misconception(
                name="会算但不能解释",
                concept="公式与图像的联系",
                description="能够得到正确数值，但不能说明数值变化对应的图像变化。",
                strength=0.7,
                correction_condition="要求学生把每一步计算和图像中的位置、倾斜程度对应起来。",
            )
        ],
    )
    _ensure_student(
        db,
        name="学生 C",
        grade="初二",
        base_level=0.6,
        personality_description="自信程度较高，回答速度快，通常先给出结论，追问理由时才暴露概念漏洞。",
        initiative=0.85,
        confidence=0.9,
        knowledge_states=[
            KnowledgeState(knowledge_point="一次函数基本定义", mastery=0.72),
            KnowledgeState(knowledge_point="一次函数基本计算", mastery=0.86),
            KnowledgeState(knowledge_point="一次函数图像基础", mastery=0.4),
            KnowledgeState(knowledge_point="k 与 b 的意义解释", mastery=0.32),
        ],
        misconceptions=[
            Misconception(
                name="先给结论再补理由",
                concept="k 与 b 的变量作用",
                description="能快速判断答案，但会把 k 和 b 的变化效果混在一起。",
                strength=0.65,
                correction_condition="要求学生预测、画图并解释理由，再检查结论是否与图像一致。",
            )
        ],
    )
    db.commit()
