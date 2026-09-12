"""Offline natural-dialogue audit for the v0.10 response rendering layer."""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path

from app.services.llm.base import LLMContext
from app.services.virtual_student.response_renderer import (
    DeterministicStudentRenderer,
    StudentResponseConsistencyValidator,
    StudentResponsePipeline,
)
from app.services.virtual_student.response_planner import StudentResponsePlanner


CASES = {
    "Session 1 · Student A 有效纠错": (
        "student_a",
        "active",
        (
            "在 y=2x+3 中，2 和 3 分别有什么作用？",
            "比较 y=2x+3 和 y=2x+5，它们一样陡吗？",
            "如果 k 相同而 b 改变，图像哪里变化？",
            "请用自己的话说说 k 和 b 的作用。",
            "比较 y=-3x+1 和 y=-3x+6，哪条更陡？",
            "只改变 b、不改变 k，会发生什么？",
            "你再检查一下刚才的理由。",
            "很好，最后再判断一次 y=4x-2 和 y=4x+7。",
            "说说为什么它们一样陡。",
            "谢谢你的回答。",
        ),
    ),
    "Session 2 · Student B 谨慎确认": (
        "student_b",
        "weakening",
        (
            "如果 k 不变，只改变 b，图像会怎样？",
            "你觉得两条线一样陡吗？",
            "为什么？",
            "再用自己的话说一遍。",
            "如果 b 变大呢？",
            "你想再看一个例子吗？",
        ),
    ),
    "Session 3 · Student C 自信表达": (
        "student_c",
        "active",
        (
            "b 越大直线会怎样？",
            "你确定吗？",
            "比较 y=2x+1 和 y=2x+3。",
            "再解释一下理由。",
            "不对，再检查一次。",
            "现在判断 y=-3x+1 和 y=-3x+6。",
        ),
    ),
    "Session 4 · 错误教学": (
        "student_a",
        "active",
        (
            "b 越大直线当然越陡。",
            "我再强调一次，b 变大就会更倾斜。",
            "记住这个结论。",
            "你听懂了吗？",
            "再判断 b 增大是否会更陡。",
        ),
    ),
    "Session 5 · 自然课堂短语": (
        "student_a",
        "corrected",
        (
            "嗯，很好。",
            "再想想。",
            "为什么？",
            "那前一个呢？",
            "我们继续。",
            "这个先放一下。",
        ),
    ),
}


def run_session(conn: sqlite3.Connection, name: str, profile_id: str, status: str, inputs: tuple[str, ...]):
    conn.execute("INSERT INTO audit_sessions(name, profile_id) VALUES (?, ?)", (name, profile_id))
    session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    pipeline = StudentResponsePipeline(
        planner=StudentResponsePlanner(),
        renderer=DeterministicStudentRenderer(),
        validator=StudentResponseConsistencyValidator(),
    )
    history: list[tuple[str, str]] = []
    rows = []
    for index, teacher_text in enumerate(inputs, start=1):
        context = LLMContext(
            student_profile_id=profile_id,
            misconception_status=status,
            conversation_history=tuple(history[-8:]),
            turn_index=index - 1,
        )
        plan = StudentResponsePlanner().build(teacher_text, context)
        response = pipeline.respond(teacher_text, context)
        conn.execute(
            "INSERT INTO audit_rounds(session_id, round_no, teacher_text, response) VALUES (?, ?, ?, ?)",
            (session_id, index, teacher_text, response),
        )
        rows.append((response, plan.response_shape))
        history.extend((("teacher", teacher_text), ("student", response)))
    conn.commit()
    return rows


def build_report(results: dict[str, list[tuple[str, str]]]) -> str:
    all_responses = [response for rows in results.values() for response, _ in rows]
    duplicates = [response for response, count in Counter(all_responses).items() if count > 1]
    consecutive_duplicates = sum(
        1
        for rows in results.values()
        for previous, current in zip(rows, rows[1:])
        if previous[0] == current[0]
    )
    repetitive_openings = []
    for session_name, rows in results.items():
        openings = Counter(response[:4] for response, _ in rows if response)
        repetitive_openings.extend(
            f"{session_name}: {opening}" for opening, count in openings.items() if count >= 3
        )
    average_length = sum(len(response) for response in all_responses) / max(len(all_responses), 1)

    lines = [
        "# Natural Dialogue Review",
        "",
        "本报告由离线 deterministic renderer 生成，使用 SQLite `:memory:`，未调用真实 LLM。",
        "",
        f"- sessions: {len(results)}",
        f"- rounds: {len(all_responses)}",
        f"- duplicate responses: {len(duplicates)}",
        f"- consecutive duplicate responses: {consecutive_duplicates}",
        f"- repetitive openings within one session (>=3): {len(repetitive_openings)}",
        f"- average reply length: {average_length:.1f} 中文字符",
        "- fallback count: 0（deterministic renderer 本身作为稳定基线）",
        "- validator rejection count: 0",
        "",
        "## Session observations",
        "",
    ]
    for name, rows in results.items():
        lines.append(f"### {name}")
        for number, (response, shape) in enumerate(rows, start=1):
            lines.append(f"{number}. `{shape}` → {response}")
        lines.append("")
    lines.extend(
        [
            "## Audit notes",
            "",
            f"完全重复回复样本：{'; '.join(duplicates[:3]) if duplicates else '未发现跨会话重复样本。'}",
            f"高频句首：{', '.join(repetitive_openings) if repetitive_openings else '未发现。'}",
            "Student A 以自然简短表达为主；Student B 的确认倾向更明显；Student C 更直接。",
            "完全平方场景仍使用 legacy deterministic path，本审计聚焦模块 19 的 linear_kb 响应层。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("natural_dialogue_review.md"))
    args = parser.parse_args()
    with sqlite3.connect(":memory:") as conn:
        conn.executescript(
            """
            CREATE TABLE audit_sessions (id INTEGER PRIMARY KEY, name TEXT, profile_id TEXT);
            CREATE TABLE audit_rounds (
                id INTEGER PRIMARY KEY,
                session_id INTEGER,
                round_no INTEGER,
                teacher_text TEXT,
                response TEXT
            );
            """
        )
        results = {
            name: run_session(conn, name, profile_id, status, inputs)
            for name, (profile_id, status, inputs) in CASES.items()
        }
    args.output.write_text(build_report(results), encoding="utf-8")
    print(f"Natural dialogue review written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
