"""Small real-provider check through the session API, always using a disposable DB."""
import json
import os
from pathlib import Path
import tempfile


def run():
    from app.core.config import get_settings
    settings = get_settings()
    output = Path(__file__).with_name('real_api_smoke.json')
    if not settings.llm_api_key:
        result = {'status':'skipped','reason':'LLM_API_KEY is not configured','session_rounds':0,'real_responses':0}
        output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
        return
    with tempfile.TemporaryDirectory(prefix='teaching-real-api-') as directory:
        os.environ['TEACHING_DATABASE_PATH'] = str(Path(directory)/'smoke.db')
        os.environ['LLM_PROVIDER'] = 'real'
        from fastapi.testclient import TestClient
        from app.main import app
        from app.database.session import engine
        turns = []
        with TestClient(app, headers={'X-Practice-Token':'d'*64}) as client:
            scenario = client.get('/api/scenarios').json()[0]['id']
            student = client.get('/api/virtual-students').json()[0]['id']
            session = client.post('/api/sessions',json={'scenario_id':scenario,'virtual_student_id':student}).json()
            for n,text in enumerate(('比较 y=1/2x+1 和 y=2x+1，哪条更陡？','谢谢你的尝试，继续解释依据。','换一道 y=-2x-3，在 x=0 时 y 是多少？')):
                response = client.post(f"/api/sessions/{session['id']}/messages",json={'teacher_text':text,'request_id':f'real-{n}','expected_version':session['version']})
                if response.status_code != 200:
                    turns.append({'http_status':response.status_code,'status':'failed'})
                    break
                session = response.json()
                student_reply = session['dialogue_records'][-1]
                turns.append({'teacher':text,'student':student_reply['content'],'metadata':json.loads(student_reply['response_metadata'])})
        engine.dispose()
    count = sum(t.get('metadata',{}).get('source') == 'real' for t in turns)
    result = {'status':'completed' if len(turns)==3 and count==3 else 'degraded_or_failed','session_rounds':len(turns),'real_responses':count,'turns':turns}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='turns'}))


if __name__ == '__main__':
    run()
