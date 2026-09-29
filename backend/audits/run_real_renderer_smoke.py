"""Small, opt-in Real Renderer smoke experiment.

This script never prints or persists the API key.  It exits safely without a
remote call unless both the provider and the explicit validation flag are set.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import get_settings
from app.services.llm.base import LLMContext
from app.services.llm.real import RealLLMClient
from app.services.virtual_student import (
    DeterministicStudentRenderer,
    RealLLMStudentRenderer,
    StudentResponseConsistencyValidator,
    StudentResponsePipeline,
    StudentResponsePlanner,
)


PHASE_A_CASES = (
    ("active_misconception_exposure", "b 越大时，直线会不会更陡？"),
    ("normal_question", "请说说 k 和 b 分别有什么作用。"),
    ("correct_direct_answer", "记住：k 决定倾斜程度，b 只改变截距和上下位置。"),
    ("incorrect_direct_answer", "对，b 越大直线就越陡。"),
    ("targeted_correction", "比较 y=2x+3 和 y=2x+5，它们的 k 都是 2。"),
    ("praise", "很好，你先继续想一想。"),
    ("out_of_scope", "请用大学线性代数解释这个一次函数。"),
)

PHASE_B_INPUTS = (
    "在 y=2x+3 中，2 和 3 分别有什么作用？",
    "如果 k 相同而 b 改变，图像哪里变化？",
    "比较 y=2x+3 和 y=2x+5，它们一样陡吗？",
    "不对，再解释一下为什么。",
    "请用自己的话说说 k 和 b 的作用。",
    "比较 y=-3x+1 和 y=-3x+6，哪条更陡？",
    "最后判断 y=4x-2 和 y=4x+7，为什么？",
    "很好，你现在听懂了吗？",
)

PROFILE_STYLES = {
    "student_a": {
        "student_name": "学生 A",
        "confidence": 0.4,
        "confidence_style": "主观自信较低，常用‘应该’‘我觉得’‘吧’等缓和表达。",
        "response_style": "回答自然、简短，先说明当前想法，再根据教师提示继续。",
        "confirmation_seeking": "喜欢先确认自己的理解。",
        "correction_style": "被直接告知答案后先记下结论，仍需独立解释。",
        "style_examples": ("我先试着说一下。", "嗯，我觉得应该是这样。", "理由还得再想想。"),
    },
    "student_b": {
        "student_name": "学生 B",
        "confidence": 0.55,
        "confidence_style": "表达偏谨慎，常先核对计算，再说明是否理解。",
        "response_style": "回答短而有步骤，计算会说出来，概念不确定时请求确认。",
        "confirmation_seeking": "经常想再确认一次，但不要每轮使用相同口头禅。",
        "correction_style": "会算不等于理解，看到理由后再逐步调整。",
        "style_examples": ("我先算一下。", "这里我想再确认。", "结果能算出来，原因还要想想。"),
    },
    "student_c": {
        "student_name": "学生 C",
        "confidence": 0.85,
        "confidence_style": "表达直接、自信，通常先给出自己的判断，但可能需要被追问。",
        "response_style": "回答简短直接，被追问时再补充理由。",
        "confirmation_seeking": "较少主动请求确认，遇到证据冲突时重新检查。",
        "correction_style": "对比例证后会调整，但仍需独立解释和迁移。",
        "style_examples": ("我先直接说我的想法。", "这个我能判断。", "我觉得就是这样。"),
    },
}


def context_for(profile_id: str, *, status: str, history: list[tuple[str, str]], turn: int) -> LLMContext:
    style = PROFILE_STYLES[profile_id]
    return LLMContext(
        student_name=style["student_name"],
        student_grade="初二",
        topic="一次函数 k 与 b 的意义",
        conversation_history=tuple(history[-6:]),
        turn_index=turn,
        student_profile_id=profile_id,
        misconception_status=status,
        misconception_strength=0.8,
        student_confidence=style["confidence"],
        confidence_style=style["confidence_style"],
        response_style=style["response_style"],
        confirmation_seeking=style["confirmation_seeking"],
        correction_style=style["correction_style"],
        style_examples=style["style_examples"],
    )


def safe_config(settings) -> dict[str, object]:
    parsed = urlparse(settings.llm_api_url)
    return {
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "endpoint_host": parsed.netloc or "未配置",
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }


def smoke_report(*, settings, status: str, reason: str | None = None) -> dict[str, object]:
    return {
        "status": status,
        "reason": reason,
        "config": safe_config(settings),
        "phase_a": {"planned_turns": 21, "completed_turns": 0},
        "phase_b": {"planned_rounds": 24, "completed_rounds": 0},
        "api": {"calls": 0, "successful_calls": 0, "api_failures": 0, "retries": 0, "fallbacks": 0, "validator_rejects": 0},
        "transcripts": {"student_a": [], "student_b": [], "student_c": []},
        "comparison": [],
        "repetition_audit": {},
    }


def record_turn(
    pipeline: StudentResponsePipeline,
    planner: StudentResponsePlanner,
    profile_id: str,
    teacher_text: str,
    status: str,
    history: list[tuple[str, str]],
    turn: int,
) -> dict[str, object]:
    context = context_for(profile_id, status=status, history=history, turn=turn)
    plan = planner.build(teacher_text, context)
    before_attempts = pipeline.total_attempts
    before_retries = pipeline.retry_count
    before_fallbacks = pipeline.fallback_count
    before_rejects = pipeline.validator_rejections
    started = time.perf_counter()
    reply = pipeline.respond(teacher_text, context)
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return {
        "round": turn + 1,
        "teacher_input": teacher_text,
        "response_goal": plan.response_goal,
        "belief_stance": plan.current_belief_stance,
        "reply": reply,
        "latency_ms": latency_ms,
        "attempts": pipeline.total_attempts - before_attempts,
        "retry": pipeline.retry_count > before_retries,
        "fallback": pipeline.fallback_count > before_fallbacks,
        "validator_rejected": pipeline.validator_rejections > before_rejects,
    }


def run_real(settings, report: dict[str, object]) -> dict[str, object]:
    client = RealLLMClient(settings)
    real_renderer = RealLLMStudentRenderer.from_client(client)
    planner = StudentResponsePlanner()
    validator = StudentResponseConsistencyValidator()
    phase_a = report["phase_a"]
    phase_b = report["phase_b"]
    transcripts = report["transcripts"]
    all_rows: list[dict[str, object]] = []

    for profile_id in PROFILE_STYLES:
        for case_id, teacher_text in PHASE_A_CASES:
            pipeline = StudentResponsePipeline(planner, real_renderer, validator)
            row = record_turn(pipeline, planner, profile_id, teacher_text, "active", [], 0)
            row["case_id"] = case_id
            row["profile_id"] = profile_id
            all_rows.append(row)
            transcripts[profile_id].append({"phase": "A", **row})
            phase_a["completed_turns"] += 1
            report["api"]["calls"] += row["attempts"]
            report["api"]["successful_calls"] += 1
            report["api"]["retries"] += int(row["retry"])
            report["api"]["fallbacks"] += int(row["fallback"])
            report["api"]["validator_rejects"] += int(row["validator_rejected"])

    statuses = ("active", "active", "weakening", "weakening", "provisional", "provisional", "provisional", "corrected")
    for profile_id in PROFILE_STYLES:
        history: list[tuple[str, str]] = []
        deterministic = StudentResponsePipeline(planner, DeterministicStudentRenderer(), validator)
        real = StudentResponsePipeline(planner, real_renderer, validator)
        for turn, (teacher_text, status) in enumerate(zip(PHASE_B_INPUTS, statuses)):
            real_row = record_turn(real, planner, profile_id, teacher_text, status, history, turn)
            mock_row = record_turn(deterministic, planner, profile_id, teacher_text, status, history, turn)
            transcripts[profile_id].append({"phase": "B", **real_row})
            report["comparison"].append({"profile_id": profile_id, "round": turn + 1, "mock_reply": mock_row["reply"], "real_reply": real_row["reply"]})
            history.extend((("teacher", teacher_text), ("student", str(real_row["reply"]))))
            phase_b["completed_rounds"] += 1
            report["api"]["calls"] += real_row["attempts"]
            report["api"]["successful_calls"] += 1
            report["api"]["retries"] += int(real_row["retry"])
            report["api"]["fallbacks"] += int(real_row["fallback"])
            report["api"]["validator_rejects"] += int(real_row["validator_rejected"])

    replies = [str(item["reply"]) for item in all_rows]
    lengths = [len(reply) for reply in replies]
    openings = Counter(reply[:4] for reply in replies if reply)
    report["repetition_audit"] = {
        "exact_duplicate_replies": len(replies) - len(set(replies)),
        "repeated_openings": {key: value for key, value in openings.items() if value > 1},
        "mean_length": round(statistics.mean(lengths), 1) if lengths else 0,
        "median_length": statistics.median(lengths) if lengths else 0,
        "longest_length": max(lengths, default=0),
        "phrase_counts": {phrase: sum(phrase in reply for reply in replies) for phrase in ("我觉得", "我想", "应该", "不太确定", "明白了")},
    }
    return report


def main() -> int:
    settings = get_settings()
    output = Path(__file__).with_name("real_renderer_smoke.md")
    report_path = Path(__file__).with_name("real_renderer_smoke.json")
    enabled = os.getenv("RUN_REAL_LLM_VALIDATION", "false").strip().lower() == "true"
    if settings.llm_provider != "real" or not enabled:
        report = smoke_report(settings=settings, status="skipped", reason="REAL_LLM_SMOKE_SKIPPED_GUARD")
        print("REAL_LLM_SMOKE_SKIPPED_GUARD")
    elif not settings.llm_api_key:
        report = smoke_report(settings=settings, status="skipped", reason="REAL_LLM_SMOKE_SKIPPED_NO_KEY")
        print("REAL_LLM_SMOKE_SKIPPED_NO_KEY")
    else:
        print("Real Renderer smoke enabled")
        print(f"Provider: {settings.llm_provider}")
        print(f"Model: {settings.llm_model}")
        print("Phase A planned turns: 21")
        print("Phase B planned rounds: 24")
        report = run_real(settings, smoke_report(settings=settings, status="completed"))

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Real Renderer Smoke",
        "",
        "本报告不保存 API Key、Authorization header、完整 system prompt 或供应商敏感 metadata。",
        "",
        f"- status: {report['status']}",
        f"- reason: {report.get('reason') or 'completed'}",
        f"- provider: {report['config']['provider']}",
        f"- model: {report['config']['model']}",
        f"- endpoint host: {report['config']['endpoint_host']}",
        f"- temperature: {report['config']['temperature']}",
        f"- max tokens: {report['config']['max_tokens']}",
        "",
        "## Call summary",
        "",
        f"- Phase A: {report['phase_a']['completed_turns']} / {report['phase_a']['planned_turns']}",
        f"- Phase B: {report['phase_b']['completed_rounds']} / {report['phase_b']['planned_rounds']}",
        f"- API calls: {report['api']['calls']}",
        f"- successful calls: {report['api']['successful_calls']}",
        f"- retries: {report['api']['retries']}",
        f"- fallbacks: {report['api']['fallbacks']}",
        f"- validator rejects: {report['api']['validator_rejects']}",
        "",
        "## Review status",
        "",
        "Mock vs Real 的 1～5 人工评分需要在真实转录生成后由评审者填写；脚本不伪造主观评分。",
        "核心认知状态由原有 Engine 负责，本脚本只传递预设状态给 Renderer，不修改状态。",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
