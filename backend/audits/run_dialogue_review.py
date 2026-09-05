"""Reproduce exploratory classroom conversations against an isolated Mock API."""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['LLM_PROVIDER'] = 'mock'

CASES = {
    'warmup': ['先别急着作答，留半分钟在心里组织一下。', '没有关系，说错也能帮助我们发现问题。', '谁愿意接着他的想法往下说？'],
    'context_after_praise': ['看 y=2x+1 和 y=2x+3，哪条更陡？', '说得不错。', '那它们与纵轴相交的位置呢？', '先把横坐标取成零，再分别算一下。'],
    'quoted_error': ['有同学说“b越大直线越陡”，你同意吗？', '我们不能说 b越大直线越陡，这个说法不正确。', '请用一个反例推翻刚才的说法。'],
    'wrong_teaching': ['记住，k 决定截距，b 决定斜率。', '因为 b 控制倾斜程度，所以增大 b 会使直线更陡。', '请复述老师刚才给出的结论。'],
    'life_context': ['出租车起步价八元，每公里再收两元，你能把路程和费用联系起来吗？', '把费用记为 y，路程记为 x，可以写成 y=2x+8。', '这里的八元对应图像的哪个特征？'],
    'numeric_variants': ['当 y=2x+3，x=0 时，y 是多少？', '如果 y=-2x+3 呢？', '比较 y=0.5x+1 和 y=0.5x+3，哪条更陡？', '再比较 y=2x+1 和 y=2.0x+3，哪条更陡？'],
    'negation': ['你的思路不是不对，只是理由还没说完整。', '不要直接告诉我答案，先把推理过程说出来。', '你现在不用再计算，先听我讲。', '我不认为你说得正确，请重新检查。'],
    'mixed_management': ['先看黑板，想想为什么这两条直线平行。', '不用举手了，直接说 k 表示什么。', '很好，但 b 表示斜率这个结论需要改。'],
    'repeated_examples': ['请比较 y=2x+1 和 y=2x+3。'] * 5,
    'real_off_topic': ['我们不讲函数了，给我推荐一部电影。', '先别讨论数学，介绍一下篮球比赛。', '请帮我计算今天买奶茶要花多少钱。'],
    'encouragement_transfer': ['我相信你可以独立判断。', '你刚才做得很好，现在换个办法试一下。', '你能完成，不着急。'],
}


def main():
    from sqlalchemy import create_engine
    import app.database.session as database
    with tempfile.TemporaryDirectory(prefix='classroom-review-') as temporary:
        database.engine.dispose()
        database.DATABASE_DIR = Path(temporary)
        database.DATABASE_PATH = Path(temporary) / 'review.db'
        database.DATABASE_URL = 'sqlite:///' + database.DATABASE_PATH.as_posix()
        database.engine = create_engine(database.DATABASE_URL, connect_args={'check_same_thread': False})
        database.SessionLocal.configure(bind=database.engine)
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.virtual_student.classroom_intent import analyze_classroom_dialogue
        from app.services.virtual_student.behavior import detect_teacher_behavior
        results = []
        try:
            with TestClient(app) as client:
                scenario = client.get('/api/scenarios').json()[0]
                students = client.get('/api/virtual-students').json()
                for student in students:
                    for case_id, turns in CASES.items():
                        created = client.post('/api/sessions', json={'scenario_id': scenario['id'], 'virtual_student_id': student['id']})
                        created.raise_for_status()
                        session_id = created.json()['id']
                        history = []
                        case = {'case': case_id, 'student': student['name'], 'rounds': []}
                        for teacher in turns:
                            response = client.post(f'/api/sessions/{session_id}/messages', json={'teacher_text': teacher})
                            response.raise_for_status()
                            data = response.json()
                            intent = analyze_classroom_dialogue(teacher, conversation_history=tuple(history[-8:]))
                            trace = data['cognitive_trace']['rounds'][-1]
                            record = {'teacher': teacher, 'student': data['dialogue_records'][-1]['content'],
                                      'acts': [a.value for a in intent.acts], 'source': intent.classification_source,
                                      'engine_behavior': detect_teacher_behavior(teacher).value,
                                      'analysis': data['behavior_records'][-1], 'trace': trace}
                            case['rounds'].append(record)
                            history.extend([('teacher', teacher), ('student', record['student'])])
                        ended = client.post(f'/api/sessions/{session_id}/end')
                        ended.raise_for_status()
                        case['evaluation'] = ended.json()['evaluation']
                        results.append(case)
        finally:
            database.engine.dispose()
    output = Path(__file__).with_name('dialogue_review_results.json')
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    checks = 0
    for case in results:
        rounds = case['rounds']
        if case['case'] == 'numeric_variants':
            assert '一样陡' in rounds[-1]['student']
            checks += 1
        elif case['case'] == 'quoted_error':
            assert rounds[0]['engine_behavior'] == 'effective_question'
            assert rounds[1]['engine_behavior'] == 'targeted_correction'
            checks += 1
        elif case['case'] == 'wrong_teaching':
            assert case['evaluation']['knowledge_accuracy'] <= 20
            checks += 1
        elif case['case'] == 'context_after_praise':
            assert '1、3' in rounds[2]['student'] and '1、3' in rounds[3]['student']
            checks += 1
        elif case['case'] == 'negation':
            assert rounds[2]['analysis']['action_type'] == 'classroom_interaction'
            checks += 1
        elif case['case'] == 'repeated_examples':
            assert rounds[0]['trace']['state_after']['understanding'] == rounds[-1]['trace']['state_after']['understanding']
            checks += 1
        elif case['case'] == 'encouragement_transfer':
            assert rounds[0]['analysis']['action_type'] == 'feedback'
            assert rounds[1]['analysis']['action_type'] == 'question'
            checks += 1
        elif case['case'] == 'life_context':
            assert 'y=2x+8' in rounds[0]['student'] and '截距' in rounds[2]['student']
            checks += 1
    print(f'Regression checkpoints passed: {checks}')
    print(json.dumps({'cases': len(results), 'rounds': sum(len(c['rounds']) for c in results), 'output': str(output)}, ensure_ascii=False))
    for case in results:
        if case['student'] != students[0]['name']:
            continue
        print('\n' + case['case'])
        for r in case['rounds']:
            print(json.dumps({'teacher': r['teacher'], 'student': r['student'], 'action': r['analysis']['action_type'],
                              'accuracy': r['analysis']['knowledge_accuracy'], 'behavior': r['engine_behavior'],
                              'understanding': [r['trace']['state_before']['understanding'], r['trace']['state_after']['understanding']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
