"""Exercise the actual API against a fresh disposable database and export evidence."""
import json
import os
from pathlib import Path
import tempfile


def run():
    output = Path(__file__).resolve().parent
    cases = json.loads((output/'classroom_acceptance_cases.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='teaching-api-audit-') as directory:
        os.environ['TEACHING_DATABASE_PATH'] = str(Path(directory)/'audit.db')
        os.environ['LLM_PROVIDER'] = 'mock'
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database.session import SessionLocal, engine
        from app.models import TrainingScenario, VirtualStudent, Misconception, KnowledgeState
        from validation.case_loader import load_student_profile, CASE_DIR
        results = []
        with TestClient(app, headers={'X-Practice-Token': 'c'*64}) as client:
            for case in cases:
                profile = load_student_profile(case['student'], path=CASE_DIR/'student_a_binomial_square.json' if case['topic']=='binomial_square' else None, misconception_type=case['topic'])
                with SessionLocal() as db:
                    scenario = TrainingScenario(title=case['id'], subject='数学', grade='初二', topic='完全平方公式' if case['topic']=='binomial_square' else '一次函数', teaching_goal='独立课堂验收', description='临时审计场景')
                    student = VirtualStudent(name=profile.name, grade=profile.grade, base_level=profile.base_level, personality_description=profile.personality_description, initiative=profile.initiative, confidence=profile.confidence,
                        knowledge_states=[KnowledgeState(knowledge_point=k.knowledge_point, mastery=k.mastery) for k in profile.knowledge_states],
                        misconceptions=[Misconception(**{key:getattr(m,key) for key in ('name','concept','description','strength','correction_condition')}) for m in profile.misconceptions])
                    db.add_all([scenario, student]); db.commit()
                    request = {'scenario_id':scenario.id,'virtual_student_id':student.id}
                session = client.post('/api/sessions', json=request).json()
                for n, teacher in enumerate(case['turns'], 1):
                    response = client.post(f"/api/sessions/{session['id']}/messages", json={'teacher_text':teacher,'request_id':f"{case['id']}-{n}",'expected_version':session['version']})
                    if response.status_code != 200:
                        raise RuntimeError(f"{case['id']} turn {n}: {response.text}")
                    session = response.json()
                ended = client.post(f"/api/sessions/{session['id']}/end")
                if ended.status_code != 200:
                    raise RuntimeError(ended.text)
                session = ended.json()
                assertions = []
                for check in case['checks']:
                    turn = session['cognitive_trace']['rounds'][check['turn']-1]
                    reply = turn['student_text']
                    passed = (check.get('contains', '') in reply and (not check.get('forbids') or check['forbids'] not in reply) and (not check.get('not_mastered') or not turn['misconception_after']['corrected']))
                    assertions.append({**check,'passed':passed})
                results.append({'id':case['id'],'topic':case['topic'],'student':case['student'],'assertions':assertions,'trace':session['cognitive_trace'],'evaluation':session['evaluation'],'dialogue':session['dialogue_records']})
        engine.dispose()
    report = {'sessions':len(results),'rounds':sum(len(c['trace']['rounds']) for c in results),'passed':all(a['passed'] for c in results for a in c['assertions']),'real_provider':'not_called_offline_audit','cases':results}
    (output/'reliability_review_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sample = next(c for c in results if c['id']=='quoted_wrong_claim')
    lines = ['# API 实训验收实例',f"通过正式会话 API，使用临时数据库和 Mock 模式。共 {report['sessions']} 段、{report['rounds']} 轮；独立断言全部通过：{report['passed']}。", f"本例：学生 {sample['student'][-1].upper()}，一次函数。辨析引用的错误观点，比较图像，纠正混淆，再使用负斜率新题检验。", '## 完整课堂实例']
    for turn in sample['trace']['rounds']:
        evidence = turn['evidence']
        before, after = turn['misconception_before'], turn['misconception_after']
        lines += [f"### 第 {turn['round']} 轮", f"教师：{turn['teacher_text']}", f"学生：{turn['student_text']}", f"状态：{before['status']} → {after['status']}；独立正确证据累计 {before['stable_correct_evidence_count']} → {after['stable_correct_evidence_count']}。本轮解释证据={evidence['explains_reason_correctly']}，迁移证据={evidence['transfer_success']}。"]
    evaluation = sample['evaluation']
    labels = {'knowledge_accuracy':'知识准确性', 'questioning':'提问', 'feedback':'反馈', 'misconception_diagnosis':'错误诊断', 'scaffolding':'支架支持', 'overall_score':'总分'}
    lines += ['## 本例评价', evaluation['summary'], f"评分版本：{evaluation['rubric_version']}；可评估权重覆盖：{evaluation['evidence']['coverage']:.0%}；独立任务：{evaluation['evidence']['independent_tasks']}。第二版分数是待专业教师校准的训练参考值。", '\n'.join(['| 维度 | 参考分 |', '|---|---:|'] + [f"| {label} | {evaluation[key] if evaluation[key] is not None else '未评估'} |" for key,label in labels.items()]), '同一题的重复解释保留在转录中，但不重复累计掌握证据。active 为错误认知仍存在，provisional 为初步修正但不稳定，corrected 为模拟引擎中达到稳定证据条件。', '## 评分引用的证据']
    for dimension, tasks in evaluation['evidence']['dimensions'].items():
        lines.append('### ' + labels[dimension])
        for task in tasks:
            if dimension == 'knowledge_accuracy':
                lines.append(f"第 {'、'.join(map(str, task['rounds']))} 轮：命题核验={task['checks']}；{task['reason']}。")
                continue
            lines.append('任务：`' + task['task'] + '`')
            for check in task['checks']:
                lines.append(f"- {check['criterion']}：{check['value']}；引用第 {'、'.join(map(str, check['rounds']))} 轮。{check['reason']}。")
    lines += ['全部 12 段课堂的机器可读转录与逐项证据见同目录 reliability_review_results.json；未评估维度与总分保留为空，不解释为零分。']
    (output/'reliability_test_example.md').write_text('\n\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'},ensure_ascii=False))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    run()
