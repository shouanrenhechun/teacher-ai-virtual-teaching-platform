import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine

from app.database.migrations import migrate
from app.services.evidence_scoring import score_session, teacher_claims
from app.services.teaching_behavior import TeachingBehaviorAnalyzer
from app.services.virtual_student.evidence import StudentResponseEvidenceAnalyzer


def observed_session(pairs):
    teachers, records, rounds = [], [], []
    history = []
    from app.services.llm.base import LLMContext
    for n, (teacher, student) in enumerate(pairs):
        result = TeachingBehaviorAnalyzer().analyze(teacher, context=LLMContext(conversation_history=tuple(history)))
        evidence = StudentResponseEvidenceAnalyzer().analyze(student, teacher_text=teacher)
        teachers.append(SimpleNamespace(id=n+1, sequence=2*n, speaker='teacher', content=teacher))
        records.append(SimpleNamespace(dialogue_record_id=n+1, action_type=result.action_type.value, concept=result.concept, gave_answer_directly=result.gave_answer_directly))
        rounds.append({'teacher_text':teacher, 'student_text':student, 'action_type':result.action_type.value, 'gave_answer_directly':result.gave_answer_directly, 'evidence':evidence.to_dict()})
        history.extend([('teacher', teacher), ('student', student)])
    return SimpleNamespace(behavior_records=records, dialogue_records=teachers, snapshot=SimpleNamespace(cognitive_trace_json=json.dumps({'rounds':rounds})))


def test_targeted_feedback_beats_empty_praise_and_duplicates_do_not_add_score():
    first = ('看 y=2x+1 和 y=2x+3，哪条更陡？', '我觉得 b 越大直线越陡。')
    good = ('你刚才把截距和斜率混淆了，b 不影响斜率。请比较两条直线，解释依据。', '两条直线一样陡，因为斜率相同，b 只改变上下位置。')
    good_session = observed_session([first, good])
    poor_session = observed_session([first, ('很好，继续。', '谢谢老师。')])
    good_scores, good_evidence = score_session(good_session)
    poor_scores, _ = score_session(poor_session)
    assert good_scores['feedback'] > poor_scores['feedback']
    assert good_scores['misconception_diagnosis'] > poor_scores['misconception_diagnosis']
    repeated_scores, repeated_evidence = score_session(observed_session([first, good, good, good]))
    assert repeated_scores == good_scores
    assert repeated_evidence['independent_tasks'] == good_evidence['independent_tasks'] == 1
    assert good_scores['overall_score'] is None


def test_independent_reasoning_beats_parroting_and_coverage_gates_total():
    pairs = []
    for k, b in [(2, 1), (-3, 2), (4, -1)]:
        pairs.extend([
            (f'比较 y={k}x+{b} 和 y={k}x+6。', '我觉得 b 越大直线越陡。'),
            ('你刚才混淆了位置与倾斜，b 不影响斜率。先比较再解释原因。', '两条直线一样陡，因为斜率相同，b 只改变上下位置。'),
        ])
    scores, evidence = score_session(observed_session(pairs))
    assert evidence['independent_tasks'] == 3
    assert evidence['coverage'] >= .8
    assert scores['overall_score'] is not None
    echoed = [(teacher, teacher) for teacher, _ in pairs]
    weak, _ = score_session(observed_session(echoed))
    assert scores['scaffolding'] > weak['scaffolding']


def test_rephrased_correct_claim_cannot_drown_out_error_on_same_task():
    initial = [('b 决定斜率。', '我还不清楚。'), ('b 只影响位置。', '我再想一想。')]
    baseline = score_session(observed_session(initial))[0]
    repeated = score_session(observed_session(initial + [('b 决定上下位置。', '我再想一想。')] * 8))[0]
    assert baseline['knowledge_accuracy'] == repeated['knowledge_accuracy'] == 50


def test_equal_steepness_is_not_equal_signed_slope():
    assert teacher_claims('y=2x+1 和 y=-2x+1 一样陡。') == [True]
    assert teacher_claims('y=2x+1 和 y=-2x+1 斜率相同。') == [False]


def test_equivalent_binomial_expansions_are_checked_as_exact_numbers():
    assert teacher_claims('(0.5x-1)^2=1-1x+1/4x^2。') == [True]
    assert teacher_claims('(0.5x-1)^2=1+1x+0.25x^2。') == [False]


def test_explicit_later_retraction_preserves_citation_but_excludes_old_claim():
    scores, evidence = score_session(observed_session([
        ('b 决定斜率。', '我再想一想。'),
        ('刚才是口误，b 不影响斜率。', '我需要再比较图像。'),
    ]))
    assert scores['knowledge_accuracy'] == 100
    assert evidence['withdrawn_claims'][0]['round'] == 1
    assert evidence['withdrawn_claims'][0]['retracted_at'] == 2


def test_qualitative_report_cites_the_same_rubric_evidence():
    from app.services.evaluation_engine import EvaluationEngine
    session = observed_session([
        ('比较 y=2x+1 和 y=2x+3。', '我觉得 b 越大直线越陡。'),
        ('你刚才混淆了截距与斜率，b 不影响斜率。请比较再解释依据。', '两条一样陡，因为斜率相同，b 只改变位置。'),
    ])
    scores, evidence = score_session(session)
    qualitative = EvaluationEngine()._fallback_qualitative(session, scores, {}, evidence)
    assert qualitative.evidence_rounds
    assert any('第 ' in line and '轮' in line for line in qualitative.strengths + qualitative.problems)


def test_fallback_student_turns_are_not_counted_as_independent_learning_evidence():
    pairs = [
        ('比较 y=2x+1 和 y=2x+3，解释为什么一样陡。', '一样陡，因为 k 相同，b 只改变上下位置。'),
        ('换成 y=-3x+2 和 y=-3x+8，说明理由。', '一样陡，因为 k 都是 -3，b 只改变位置。'),
        ('再看 y=4x-1 和 y=4x+6，独立解释。', '一样陡，因为 k 都是 4，b 改变上下位置。'),
    ]
    real_session = observed_session(pairs)
    fallback_session = observed_session(pairs)
    for index, teacher in enumerate(list(fallback_session.dialogue_records)):
        fallback_session.dialogue_records.append(SimpleNamespace(
            id=100 + index,
            sequence=teacher.sequence + 1,
            speaker='student',
            content=pairs[index][1],
            response_metadata=json.dumps({
                'source': 'deterministic_fallback',
                'learning_evidence_allowed': False,
            }),
        ))

    real_scores, _ = score_session(real_session)
    fallback_scores, fallback_evidence = score_session(fallback_session)
    assert fallback_evidence['excluded_fallback_response_rounds'] == [1, 2, 3]
    assert fallback_scores['scaffolding'] < real_scores['scaffolding']
    for entry in fallback_evidence['dimensions']['scaffolding']:
        checks = entry['checks']
        assert checks[1]['value'] == 0
        assert checks[2]['value'] == 0


def test_rubric_citations_distinguish_teacher_scaffold_from_student_evidence():
    session = observed_session([
        ('比较 y=2x+1 和 y=2x+3，哪条更陡？', '我觉得 b 越大直线越陡。'),
        ('你刚才把斜率和位置混淆了。先固定 k 比较两条线，再解释理由。', '一样陡，因为 k 相同，b 只改变上下位置。'),
    ])
    _, evidence = score_session(session)
    scaffold = evidence['dimensions']['scaffolding'][0]['checks']
    assert scaffold[0]['teacher_rounds'] == [1]
    assert scaffold[0]['student_rounds'] == []
    assert scaffold[1]['teacher_rounds'] == []
    assert scaffold[1]['student_rounds'] == [1]
    assert scaffold[2]['teacher_rounds'] == [2]
    assert scaffold[2]['student_rounds'] == [2]

    feedback = evidence['dimensions']['feedback'][0]['checks'][0]
    assert feedback['teacher_rounds'] == [2]
    assert feedback['student_rounds'] == [1]
    assert '教师第2轮' in feedback['reason']
    assert '学生第1轮' in feedback['reason']


def test_direct_answer_flag_overrides_misclassified_action_for_scaffolding():
    session = observed_session([
        ('我直接告诉你：k 决定倾斜程度，b 只改变位置；再比较两条直线并解释理由。',
         '两条一样陡，因为 k 相同，b 只改变上下位置。'),
    ])
    session.behavior_records[0].action_type = 'guided_question'
    session.behavior_records[0].gave_answer_directly = True
    _, evidence = score_session(session)
    checks = evidence['dimensions']['scaffolding'][0]['checks']
    assert [check['value'] for check in checks] == [0, 0, 0]


def test_diagnosis_can_refer_back_to_an_error_and_be_verified_in_a_later_task():
    scores, evidence = score_session(observed_session([
        ('比较 y=2x+1 和 y=2x+3。', '我觉得 b 越大直线越陡。'),
        ('再看一下两条直线。', '两条一样陡，因为斜率相同，b 只改变位置。'),
        ('你刚才混淆了截距与斜率，b 不影响斜率。', '我先记住这个结论，还需要新题确认。'),
        ('换成 y=-3x+1 和 y=-3x+8，独立解释依据。', '两条一样陡，因为斜率相同，b 只改变位置。'),
    ]))
    assert scores['misconception_diagnosis'] > 0
    checks = evidence['dimensions']['misconception_diagnosis'][0]['checks']
    assert checks[0]['value'] == 1
    assert 1 in checks[0]['rounds']
    assert checks[2]['value'] == 1
    assert checks[2]['rounds'] == [4]


def test_legacy_migration_backs_up_preserves_records_and_is_repeatable(tmp_path):
    path = tmp_path/'legacy.db'
    with sqlite3.connect(path) as conn:
        conn.executescript('''
        CREATE TABLE teaching_sessions(id INTEGER PRIMARY KEY, status TEXT);
        INSERT INTO teaching_sessions VALUES(7,'completed');
        CREATE TABLE dialogue_records(id INTEGER PRIMARY KEY,session_id INTEGER,sequence INTEGER,content TEXT);
        INSERT INTO dialogue_records VALUES(11,7,0,'原来的授课话语');
        CREATE TABLE evaluations(session_id INTEGER PRIMARY KEY,knowledge_accuracy REAL NOT NULL,questioning REAL NOT NULL,feedback REAL NOT NULL,misconception_diagnosis REAL NOT NULL,scaffolding REAL NOT NULL,overall_score REAL NOT NULL,summary TEXT NOT NULL);
        INSERT INTO evaluations VALUES(7,80,60,50,70,40,65,'旧版报告');
        CREATE TABLE evaluation_narratives(session_id INTEGER PRIMARY KEY REFERENCES evaluations(session_id),body TEXT);
        INSERT INTO evaluation_narratives VALUES(7,'原始评价证据');
        ''')
    engine = create_engine(f'sqlite:///{path.as_posix()}')
    try:
        migrate(engine)
        migrate(engine)
        with sqlite3.connect(path) as conn:
            assert conn.execute('SELECT overall_score,rubric_version FROM evaluations').fetchone() == (65,1)
            assert conn.execute('SELECT owner_hash,version FROM teaching_sessions').fetchone() == (None,0)
            assert conn.execute('SELECT body FROM evaluation_narratives').fetchone()[0] == '原始评价证据'
            assert conn.execute('SELECT content FROM dialogue_records').fetchone()[0] == '原来的授课话语'
            conn.execute('UPDATE evaluations SET overall_score=NULL')
        backups = list(tmp_path.glob('*.v1.bak'))
        assert len(backups) == 1
        with sqlite3.connect(backups[0]) as conn:
            assert conn.execute('SELECT overall_score FROM evaluations').fetchone()[0] == 65
    finally:
        engine.dispose()
