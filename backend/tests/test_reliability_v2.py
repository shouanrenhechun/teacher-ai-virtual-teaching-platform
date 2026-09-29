from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy import select

from app.main import app
from app.database.session import SessionLocal
from app.api.llm_routes import llm_client_dependency
from app.models import TeachingSession, TrainingScenario, VirtualStudent, KnowledgeState, Misconception
from app.services.llm.mock import MockLLMClient
from app.services.llm.base import LLMContext
from app.services.llm.real import RealLLMClient
from app.core.config import Settings
from app.services.virtual_student import StudentResponsePlanner, StudentResponsePipeline, DeterministicStudentRenderer
from app.services.virtual_student.response_renderer import StudentResponseConsistencyValidator
from app.services.evidence_scoring import score_session, teacher_claims


def create(client):
    scenario = client.get('/api/scenarios').json()[0]['id']
    student = client.get('/api/virtual-students').json()[0]['id']
    response = client.post('/api/sessions', json={'scenario_id': scenario, 'virtual_student_id': student})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize('text,expected', [
    ('比较 y=1/2x+1 和 y=2x+1，哪条更陡？', '2'),
    ('比较 y=-0.25x+2 和 y=0.5x-2，哪条更陡？', '1/2'),
    ('比较 y=-3/2x+2 和 y=3/2x-5，哪条更陡？', '一样陡'),
    ('计算 y=2x-3 在 x=1/2 时的值。', '-2'),
])
def test_exact_numeric_response(text, expected):
    client = MockLLMClient()
    response = client.respond(text)
    assert expected in response
    assert '+-' not in response
    assert client.last_response_metadata['source'] == 'mock'


def test_validator_rejects_bad_facts_and_safe_terminal_fallback():
    plan = StudentResponsePlanner().build('看 y=2x-3，这个常数对应图像的哪个特征？')
    validator = StudentResponseConsistencyValidator()
    assert not validator.validate(plan, '-3 元是起步价。').passed
    class Broken(DeterministicStudentRenderer):
        def render(self, *args):
            raise ValueError('broken')
    pipeline = StudentResponsePipeline(StudentResponsePlanner(), Broken(), fallback=Broken())
    assert '条件' in pipeline.respond('比较 y=2x+1 和 y=3x+2。')
    assert pipeline.last_metadata['learning_evidence_allowed'] is False


def test_validator_rejects_wrong_comparisons_and_expansions_with_plausible_reasons():
    planner, validator = StudentResponsePlanner(), StudentResponseConsistencyValidator()
    plan = planner.build('比较 y=1/2x+1 和 y=2x+1，哪条更陡？')
    assert not validator.validate(plan, '1/2 比 2 更陡，因为 1/2 的绝对值更大。').passed
    plan = planner.build('比较 y=2x+1 和 y=-2x+1，哪条更陡？')
    assert not validator.validate(plan, '两条一样陡，因为斜率相同。').passed
    plan = planner.build('把 (x+2)^2 写成两个括号相乘，解释交叉项。', LLMContext(topic='完全平方公式', misconception_semantic_type='binomial_square'))
    assert not validator.validate(plan, '得到 x²+8x+4，因为两个交叉项合并成 8x。').passed
    assert validator.validate(plan, '得到 4+4x+1.0x²，因为两个交叉项合并成 4x。').passed


def test_invalid_fraction_and_broken_validator_take_bounded_safe_fallback():
    class Invalid(DeterministicStudentRenderer):
        def render(self, *args):
            return 'y=1/0。'
    pipeline = StudentResponsePipeline(StudentResponsePlanner(), Invalid())
    assert '-2' in pipeline.respond('计算 y=2x-3 在 x=1/2 时的值。')
    assert pipeline.last_metadata['retries'] == 1
    assert pipeline.last_metadata['source'] == 'deterministic_fallback'
    class BrokenValidator:
        def validate(self, *args):
            raise ValueError('broken')
    pipeline = StudentResponsePipeline(StudentResponsePlanner(), Invalid(), validator=BrokenValidator())
    assert '条件' in pipeline.respond('计算 y=2x-3 在 x=1/2 时的值。')
    assert pipeline.last_metadata['learning_evidence_allowed'] is False


def test_binomial_instruction_only_produces_recall_not_a_fabricated_explanation():
    client = MockLLMClient()
    text = '记住：(a+b)^2=a²+2ab+b²。'
    reply = client.respond(text, LLMContext(topic='完全平方公式', misconception_semantic_type='binomial_square'))
    assert '还不太确定' in reply
    assert '因为' not in reply
    from app.services.virtual_student.evidence import StudentResponseEvidenceAnalyzer
    evidence = StudentResponseEvidenceAnalyzer().analyze(reply, teacher_text=text, misconception=SimpleNamespace(semantic_type='binomial_square'))
    assert evidence.evidence_insufficient


def test_owner_isolation_and_explicit_idempotent_legacy_import():
    with TestClient(app) as first:
        session = create(first)
        with TestClient(app, headers={'X-Practice-Token': 'b'*64}) as second:
            assert second.get(f"/api/sessions/{session['id']}").status_code == 404
            assert second.post(f"/api/sessions/{session['id']}/end").status_code == 404
            assert second.post(f"/api/sessions/{session['id']}/messages", json={'teacher_text':'尝试访问其他浏览器的课堂'}).status_code == 404
            assert second.get(f"/api/sessions/{session['id']}/evaluation").status_code == 404
            assert second.post(f"/api/sessions/{session['id']}/evaluation").status_code == 404
            assert create(second)['id'] != session['id']
        with SessionLocal() as db:
            record = db.get(TeachingSession, session['id'])
            record.owner_hash = None
            db.commit()
        assert first.get(f"/api/sessions/{session['id']}").status_code == 404
        assert first.post('/api/sessions/import-legacy').json()['imported'] == 1
        assert first.post('/api/sessions/import-legacy').json()['imported'] == 0
        assert first.get(f"/api/sessions/{session['id']}").status_code == 200


def test_message_idempotency_and_version_conflict():
    with TestClient(app) as client:
        session = create(client)
        url = f"/api/sessions/{session['id']}/messages"
        payload = {'teacher_text': '比较 y=2x+1 和 y=2x+3。', 'request_id': 'once', 'expected_version': 0}
        first = client.post(url, json=payload)
        assert first.status_code == 200, first.text
        again = client.post(url, json=payload)
        assert again.json()['dialogue_records'] == first.json()['dialogue_records']
        assert again.json()['version'] == 1
        assert client.post(url, json={**payload, 'teacher_text': '不同内容'}).status_code == 409
        assert client.post(url, json={**payload, 'request_id': 'new'}).status_code == 409
        assert client.get(f"/api/sessions/{session['id']}").json()['started_at'].endswith('+00:00')


def test_followups_and_praise_do_not_turn_one_task_into_multiple_mastery_evidence():
    with TestClient(app) as client:
        session = create(client)
        url = f"/api/sessions/{session['id']}/messages"
        counts = []
        for text in ('比较 y=2x+1 和 y=2x+6。', '比较它们为什么一样陡。', '很好。', '继续说说这两条线为什么一样陡。'):
            response = client.post(url, json={'teacher_text':text})
            assert response.status_code == 200, response.text
            misconception = response.json()['cognitive_trace']['current_misconception']
            counts.append(misconception['stable_correct_evidence_count'])
            assert not misconception['corrected']
        assert max(counts) == 1


def test_legacy_evidence_keys_are_restored_without_replaying_learning():
    with TestClient(app) as client:
        session = create(client)
        url = f"/api/sessions/{session['id']}/messages"
        first = client.post(url, json={'teacher_text':'比较 y=2x+1 和 y=2x+6。'}).json()
        from app.models import TeachingSessionSnapshot
        with SessionLocal() as db:
            snapshot = db.get(TeachingSessionSnapshot, session['id'])
            state = json.loads(snapshot.engine_state_json)
            state.pop('learning_evidence_key_version', None)
            state['learning_evidence_keys'] = ['old-text-key']
            snapshot.engine_state_json = json.dumps(state)
            db.commit()
        second = client.post(url, json={'teacher_text':'比较它们为什么一样陡。'}).json()
        assert second['cognitive_trace']['current_misconception']['stable_correct_evidence_count'] == first['cognitive_trace']['current_misconception']['stable_correct_evidence_count']


def test_concurrent_messages_commit_one_complete_round():
    barrier = Barrier(2)
    class Delayed(MockLLMClient):
        def respond(self, text, context=None):
            barrier.wait(timeout=5)
            return super().respond(text, context)
    with TestClient(app) as client:
        session = create(client)
        app.dependency_overrides[llm_client_dependency] = Delayed
        try:
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(client.post, f"/api/sessions/{session['id']}/messages", json={'teacher_text': '比较 y=2x+1 和 y=2x+3。', 'request_id': str(i), 'expected_version': 0}) for i in range(2)]
                assert sorted(f.result().status_code for f in futures) == [200, 409]
        finally:
            app.dependency_overrides.pop(llm_client_dependency)
        detail = client.get(f"/api/sessions/{session['id']}").json()
        assert len(detail['dialogue_records']) == 2
        assert len(detail['cognitive_trace']['rounds']) == 1


def test_ending_during_model_call_cannot_save_half_round_or_reopen_session():
    entered, released = Event(), Event()
    class Delayed(MockLLMClient):
        def respond(self, text, context=None):
            entered.set()
            assert released.wait(5)
            return super().respond(text, context)
    with TestClient(app) as client:
        session = create(client)
        app.dependency_overrides[llm_client_dependency] = Delayed
        try:
            with ThreadPoolExecutor(1) as pool:
                pending = pool.submit(client.post, f"/api/sessions/{session['id']}/messages", json={'teacher_text':'比较 y=2x+1 和 y=2x+3。'})
                try:
                    assert entered.wait(5)
                    ended = client.post(f"/api/sessions/{session['id']}/end")
                    assert ended.status_code == 200, ended.text
                finally:
                    released.set()
                assert pending.result(timeout=5).status_code == 409
        finally:
            released.set()
            app.dependency_overrides.pop(llm_client_dependency)
        detail = client.get(f"/api/sessions/{session['id']}").json()
        assert detail['status'] == 'completed'
        assert detail['dialogue_records'] == []


def test_concurrent_report_generation_returns_one_persisted_report():
    from sqlalchemy import delete, func
    from app.models import Evaluation, EvaluationNarrative
    barrier = Barrier(2)
    class DelayedEvaluation(MockLLMClient):
        provider = 'fake-real-evaluation'
        def analyze_evaluation(self, *args):
            barrier.wait(timeout=5)
            return {'strengths': ['保留了对话'], 'problems': ['证据不足'], 'suggestions': ['继续实训'], 'evidence_rounds': []}
    with TestClient(app) as client:
        session = create(client)
        client.post(f"/api/sessions/{session['id']}/end")
        with SessionLocal() as db:
            db.execute(delete(EvaluationNarrative))
            db.execute(delete(Evaluation))
            db.commit()
        app.dependency_overrides[llm_client_dependency] = DelayedEvaluation
        try:
            with ThreadPoolExecutor(2) as pool:
                futures = [pool.submit(client.post, f"/api/sessions/{session['id']}/evaluation") for _ in range(2)]
                responses = [future.result(timeout=10) for future in futures]
        finally:
            app.dependency_overrides.pop(llm_client_dependency)
        assert [response.status_code for response in responses] == [200, 200]
        assert responses[0].json() == responses[1].json()
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(Evaluation)) == 1
            assert db.scalar(select(func.count()).select_from(EvaluationNarrative)) == 1


def test_legacy_score_is_preserved_even_when_narrative_is_missing():
    from sqlalchemy import delete
    from app.models import Evaluation, EvaluationNarrative
    with TestClient(app) as client:
        session = create(client)
        client.post(f"/api/sessions/{session['id']}/end")
        with SessionLocal() as db:
            evaluation = db.get(Evaluation, session['id'])
            evaluation.rubric_version = 1
            evaluation.overall_score = 37
            db.execute(delete(EvaluationNarrative))
            db.commit()
        report = client.post(f"/api/sessions/{session['id']}/evaluation").json()
        assert report['rubric_version'] == 1
        assert report['overall_score'] == 37


@pytest.mark.parametrize('failure', ['wrong_math', 'invalid_json', 'timeout'])
def test_real_session_entrypoint_is_planned_validated_and_audited(monkeypatch, failure):
    requests = []
    class HTTP:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, *, headers, json):
            requests.append(json)
            if failure == 'timeout':
                raise httpx.TimeoutException('simulated timeout')
            content = 'not-json' if failure == 'invalid_json' else '{"reply":"我完全理解了，2 元是起步价。"}'
            return httpx.Response(200, json={'choices': [{'message': {'content': content}}]})
    monkeypatch.setattr('app.services.llm.real.httpx.Client', HTTP)
    real = RealLLMClient(Settings('real', 'fake', 'https://example.invalid/chat', 'test', 1))
    with TestClient(app) as client:
        session = create(client)
        app.dependency_overrides[llm_client_dependency] = lambda: real
        try:
            response = client.post(f"/api/sessions/{session['id']}/messages", json={'teacher_text': '比较 y=1/2x+1 和 y=2x+1，哪条更陡？'})
        finally:
            app.dependency_overrides.pop(llm_client_dependency)
    assert response.status_code == 200, response.text
    data = response.json()['dialogue_records'][-1]
    metadata = json.loads(data['response_metadata'])
    assert metadata['source'] == 'deterministic_fallback'
    assert metadata['retries'] == 1
    assert metadata['learning_evidence_allowed'] is False
    trace_round = response.json()['cognitive_trace']['rounds'][-1]
    assert trace_round['response_source'] == 'deterministic_fallback'
    assert trace_round['learning_evidence_allowed'] is False
    assert trace_round['evidence']['evidence_insufficient'] is True
    if failure == 'wrong_math':
        assert metadata['failure_category'] == 'validation_rejection'
    else:
        assert metadata['render_errors']
    assert all('test' not in str(error).lower() for error in metadata['render_errors'])
    assert '元' not in data['content']
    assert any('教师本轮话语' in call['messages'][-1]['content'] for call in requests)
    render_prompts = [call['messages'][-1]['content'] for call in requests if '教师本轮话语' in call['messages'][-1]['content']]
    assert len(render_prompts) == 2
    assert '上一候选回答违反了以下约束' not in render_prompts[0]
    assert '上一候选回答违反了以下约束' in render_prompts[1]


def test_unassessed_report_and_paginated_owned_history():
    with TestClient(app) as client:
        for i in range(12):
            session = create(client)
            response = client.post(f"/api/sessions/{session['id']}/end")
            assert response.status_code == 200, response.text
            report = response.json()['evaluation']
            assert report['overall_score'] is None
            assert report['knowledge_accuracy'] is None
            assert report['rubric_version'] == 2
        first = client.get('/api/sessions/history').json()
        second = client.get('/api/sessions/history?page=2').json()
        assert first['total'] == 12 and len(first['items']) == 10
        assert len(second['items']) == 2
        assert first['items'][0]['id'] > second['items'][0]['id']


def test_withdrawn_or_quoted_claims_are_not_assertions():
    assert teacher_claims('b 决定斜率。口误，更正为 b 只改变位置。') == [True]
    assert teacher_claims('有同学说 b 决定斜率，你同意吗？') == []


CASES = json.loads((Path(__file__).parents[1] / 'audits/classroom_acceptance_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_independent_classroom_conversation(case, tmp_path):
    from validation.case_loader import load_student_profile
    from app.services.virtual_student import VirtualStudentEngine
    profile = load_student_profile(case['student'], path=Path(__file__).parents[1] / 'validation/cases/student_a_binomial_square.json' if case['topic'] == 'binomial_square' else None, misconception_type=case['topic'])
    engine = VirtualStudentEngine(profile)
    client = MockLLMClient()
    history, actual = [], []
    from app.services.virtual_student.task_context import active_task
    for n, text in enumerate(case['turns'], 1):
        opportunity = engine.get_correction_opportunity(text)
        engine.update_from_teacher_text(text)
        state = engine.snapshot().misconceptions[0]
        context = LLMContext(topic='完全平方公式' if case['topic'] == 'binomial_square' else '一次函数', student_profile_id=case['student'], misconception_semantic_type=case['topic'], misconception_status=state.status, misconception_strength=state.strength, conversation_history=tuple(history), task_context=active_task(history, text), turn_index=n-1)
        reply = client.respond(text, context)
        engine.apply_student_response_evidence(reply, text, opportunity, previous_teacher_text=next((t for role,t in reversed(history) if role=='teacher'), ''), task_context=context.task_context)
        history.extend([('teacher',text), ('student',reply)])
        after = engine.snapshot().misconceptions[0]
        actual.append({'teacher':text, 'student':reply, 'status':after.status, 'strength':after.strength, 'source':client.last_response_metadata})
        for check in (c for c in case['checks'] if c['turn'] == n):
            if 'contains' in check: assert check['contains'] in reply, (text, reply)
            if 'forbids' in check: assert check['forbids'] not in reply, (text, reply)
            if check.get('not_mastered'): assert not after.corrected
    (tmp_path / (case['id']+'.json')).write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding='utf-8')
