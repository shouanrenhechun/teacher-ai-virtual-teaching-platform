"""Version 2 training rubric. Evidence checks are bounded and auditable, not calibrated grades."""
import json
import re
from collections import defaultdict

from .virtual_student.task_context import active_task, task_identity
from .virtual_student.propositions import assess_claims
from .virtual_student.linear_math import equations, number, quadratic_coefficients
from .virtual_student.binomial_plan import binomials, polynomial

WEIGHTS = {'knowledge_accuracy': .30, 'questioning': .20, 'feedback': .15, 'misconception_diagnosis': .20, 'scaffolding': .15}
CHECKS = {
    'questioning': ('条件明确', '保留学生作答空间', '要求解释或承接学生回答'),
    'feedback': ('对应学生实际回答', '指出具体过程或问题', '提供可执行的下一步'),
    'misconception_diagnosis': ('识别已暴露的错误', '提供正确反例或依据', '通过后续独立回答检验'),
    'scaffolding': ('提供适当中间步骤', '学生实际参与', '转向独立解释或迁移'),
}


def effective_claim_text(text):
    # An explicit self-correction withdraws the earlier claim in the same turn.
    parts = re.split(r'口误[，,:：]?|更正为[：:]?|改成[：:]?\s*(?=y=|\()', text)
    return parts[-1]


def claim_units(text):
    text = effective_claim_text(text)
    result = []
    for clause in re.split(r'[。；;]', text):
        assessment = assess_claims(clause)
        result.extend(assessment.claims)
        compact = re.sub(r'\s+', '', clause).replace('²', '^2')
        if any(word in clause for word in ('？', '?', '是否', '对不对', '有人说', '有同学说')):
            continue
        if '(a+b)^2=a^2+2ab+b^2' in compact or '(a-b)^2=a^2-2ab+b^2' in compact:
            result.append(('binomial:identity', True))
        for k, b in binomials(clause):
            match = re.search(r'\)\^2=([^，。；]+)', compact)
            if match:
                observed = quadratic_coefficients(match[1])
                if observed is not None:
                    result.append(('binomial:expansion:' + repr((k, b)), observed == quadratic_coefficients(polynomial(k, b))))
        lines = equations(clause)
        if len(lines) >= 2:
            if any(word in clause for word in ('一样陡', '同样陡')):
                result.append(('linear:steepness:' + repr(sorted(lines)), abs(number(lines[0][0])) == abs(number(lines[1][0]))))
            if '斜率相同' in clause:
                result.append(('linear:slope:' + repr(sorted(lines)), number(lines[0][0]) == number(lines[1][0])))
    return result


def teacher_claims(text):
    return [truth for _, truth in claim_units(text)]


def score_session(session):
    snapshot = getattr(session, 'snapshot', None)
    trace = json.loads(snapshot.cognitive_trace_json) if snapshot else {'rounds': []}
    rounds = [dict(item) for item in trace.get('rounds', [])]
    teachers = sorted((r for r in getattr(session, 'dialogue_records', []) if r.speaker == 'teacher'), key=lambda r: r.sequence)
    dialogue_by_sequence = {r.sequence: r for r in getattr(session, 'dialogue_records', [])}
    response_sources = []
    excluded_fallback_rounds = []
    for index, item in enumerate(rounds):
        teacher = teachers[index] if index < len(teachers) else None
        student = dialogue_by_sequence.get(teacher.sequence + 1) if teacher is not None else None
        metadata = {}
        raw_metadata = getattr(student, 'response_metadata', None) if student is not None else None
        if isinstance(raw_metadata, dict):
            metadata = raw_metadata
        elif isinstance(raw_metadata, str):
            try:
                parsed = json.loads(raw_metadata)
                metadata = parsed if isinstance(parsed, dict) else {}
            except (TypeError, ValueError):
                metadata = {}
        source = item.get('response_source') or metadata.get('source')
        allowed = item.get('learning_evidence_allowed')
        if not isinstance(allowed, bool):
            allowed = metadata.get('learning_evidence_allowed')
        if source in {'deterministic_fallback', 'clarification_fallback'}:
            allowed = False
        elif not isinstance(allowed, bool):
            allowed = True  # Preserve scoring for legacy records without provenance.
        item['_response_source'] = source or 'legacy_unclassified'
        item['_learning_evidence_allowed'] = allowed
        response_sources.append({'round': index + 1, 'source': item['_response_source'], 'learning_evidence_allowed': allowed})
        if not allowed:
            excluded_fallback_rounds.append(index + 1)
    withdrawals = []
    claim_history = []
    withdrawn = set()
    for n, item in enumerate(rounds, 1):
        units = claim_units(item['teacher_text'])
        if re.search(r'口误|更正|刚才.*(?:说错|不对)', item['teacher_text']):
            for key, truth in units:
                for old_round, old_key, old_truth in reversed(claim_history):
                    if old_key == key and old_truth != truth:
                        withdrawn.add((old_round, old_key, old_truth))
                        withdrawals.append({'round': old_round, 'retracted_at': n, 'claim': key, 'reason': '教师明确撤回先前主张并给出更正'})
        claim_history.extend((n, key, truth) for key, truth in units)
    records = list(session.behavior_records)
    behaviors = {r.dialogue_record_id: r for r in records if hasattr(r, 'dialogue_record_id')}
    groups = defaultdict(list)
    round_tasks = {}
    history = []
    for index, round_item in enumerate(rounds):
        text = round_item['teacher_text']
        task = active_task(history, text)
        identity = task_identity(effective_claim_text(text), task)
        round_tasks[index+1] = identity
        history.extend([('teacher', text), ('student', round_item['student_text'])])
        behavior = behaviors.get(teachers[index].id) if index < len(teachers) else None
        previous = rounds[index-1] if index else None
        previous_evidence = (previous or {}).get('evidence') or {}
        missed_opportunity = previous_evidence.get('shows_residual_misconception') or previous_evidence.get('conceptual_uncertainty')
        if not identity or (behavior and behavior.concept == '课堂互动' and not missed_opportunity):
            continue
        groups[identity].append((index+1, round_item, previous, behavior, task))

    evidence = {
        'rubric_version': 2,
        'independent_tasks': len(groups),
        'coverage': 0.0,
        'dimensions': {},
        'withdrawn_claims': withdrawals,
        'response_sources': response_sources,
        'excluded_fallback_response_rounds': excluded_fallback_rounds,
        'limitations': ['训练参考规则，尚待专业教师人工校准。'],
    }
    samples = defaultdict(list)
    known = []
    for identity, events in groups.items():
        checks = {name: [0., 0., 0.] for name in CHECKS}
        citations = {name: [[], [], []] for name in CHECKS}
        citation_roles = {
            name: [{'teacher_rounds': [], 'student_rounds': []} for _ in range(3)]
            for name in CHECKS
        }
        opportunities = set()
        seen_claims = set()
        task_claims = set()
        diagnosis_started = False
        for n, item, previous, behavior, task in events:
            text = effective_claim_text(item['teacher_text'])
            normalized = re.sub(r'\s+', '', text.lower())
            action = getattr(behavior, 'action_type', item.get('action_type'))
            current_evidence = item.get('evidence') or {}
            response_learning_allowed = item.get('_learning_evidence_allowed', True)
            previous_evidence = (previous or {}).get('evidence') or {}
            prior_text = (previous or {}).get('student_text', '')
            direct = (
                action == 'direct_answer'
                or bool(getattr(behavior, 'gave_answer_directly', False))
                or bool(item.get('gave_answer_directly', False))
            )
            wrong = previous_evidence.get('shows_residual_misconception') or previous_evidence.get('conceptual_uncertainty')
            independent = bool(response_learning_allowed and current_evidence.get('explains_reason_correctly') and not current_evidence.get('parrots_teacher') and not current_evidence.get('shows_residual_misconception') and not current_evidence.get('conceptual_uncertainty'))
            addresses = bool(prior_text and (any(word in text for word in ('你刚才', '刚才', '你的', '你说', '这个判断', '这个结论', '这个说法')) or any(word in text and word in prior_text for word in ('斜率', '截距', '中间项', '交叉', '倾斜', '陡'))))
            reason = any(word in text for word in ('为什么', '理由', '依据', '说明', '解释', '怎么想'))
            next_step = any(word in text for word in ('请', '试着', '再算', '比较', '代入', '展开', '观察', '说说', '看看', '画出'))
            units = [(key, truth) for key, truth in claim_units(text) if (n, key, truth) not in withdrawn]
            claims = [truth for _, truth in units]
            if claims and normalized not in seen_claims:
                seen_claims.add(normalized)
                # Repeating a correct sentence cannot drown out a conflicting claim on the same task.
                task_claims.update(units)
                evidence['dimensions'].setdefault('knowledge_accuracy', []).append({'task': identity, 'rounds': [n], 'checks': claims, 'reason': '只核验明确主张，撤回的口误及待辨析问题不计入'})

            def record(name, values, *, teacher_rounds=None, student_rounds=None):
                opportunities.add(name)
                for i, value in enumerate(values):
                    teacher_refs = teacher_rounds[i] if teacher_rounds is not None else [n]
                    student_refs = student_rounds[i] if student_rounds is not None else []
                    round_refs = sorted(set([*teacher_refs, *student_refs]))
                    if value > checks[name][i]:
                        checks[name][i] = float(value)
                        citations[name][i] = round_refs
                        citation_roles[name][i] = {
                            'teacher_rounds': list(teacher_refs),
                            'student_rounds': list(student_refs),
                        }
                    elif value == checks[name][i] and not citations[name][i] and round_refs:
                        citations[name][i] = round_refs
                        citation_roles[name][i] = {
                            'teacher_rounds': list(teacher_refs),
                            'student_rounds': list(student_refs),
                        }

            if action in {'question', 'guided_question', 'understanding_check'} or reason:
                record('questioning', [1 if task else .5, 0 if direct else 1, 1 if reason or addresses else .5 if action == 'understanding_check' else 0])
            if prior_text and (previous_evidence.get('evidence_level', 0) > 0 or wrong):
                specific = addresses and any(word in text for word in ('因为', '所以', '漏', '斜率', '截距', '中间项', '交叉', '固定', '改变', '不对', '正确'))
                record(
                    'feedback',
                    [1 if addresses else 0, 1 if specific else 0, 1 if addresses and next_step else .5 if next_step else 0],
                    teacher_rounds=[[n], [n], [n]],
                    student_rounds=[[n-1], [n-1], [n-1]],
                )
            def same_domain(round_number):
                return round_tasks.get(round_number, '').startswith(('square:', 'concept:binomial')) == identity.startswith(('square:', 'concept:binomial'))
            correct_support = False
            earlier_errors = [i+1 for i, old in enumerate(rounds[:n-1]) if same_domain(i+1) and (old.get('evidence') or {}).get('shows_residual_misconception')]
            refers_back = any(word in text for word in ('你刚才', '刚才', '你说', '这个说法', '这个判断', '这个结论'))
            diagnostic_cue = any(word in text for word in ('不对', '混淆', '漏', '不是', '不影响', '不能', '错误'))
            if wrong or (refers_back and diagnostic_cue and earlier_errors):
                identified = addresses and any(word in text for word in ('不对', '混淆', '漏', '不是', '不影响', '不能', '错误', '区别', '比较'))
                correct_support = bool(claims and all(claims)) or bool(addresses and (len(equations(text)) >= 2 or '交叉' in text))
                diagnosis_started |= identified or (addresses and correct_support)
                record(
                    'misconception_diagnosis',
                    [1 if identified else .5 if addresses else 0, 1 if correct_support else 0, 0],
                    teacher_rounds=[[n], [n], []],
                    student_rounds=[[n-1], [n-1], []],
                )
                for check_index in range(2):
                    if earlier_errors and earlier_errors[-1] not in citations['misconception_diagnosis'][check_index]:
                        citations['misconception_diagnosis'][check_index].append(earlier_errors[-1])
                        citation_roles['misconception_diagnosis'][check_index]['student_rounds'].append(earlier_errors[-1])
            if diagnosis_started and independent:
                record(
                    'misconception_diagnosis', [0, 0, 1],
                    teacher_rounds=[[], [], [n]],
                    student_rounds=[[], [], [n]],
                )
            if diagnosis_started and correct_support:
                # A later independent response can verify an intervention even
                # when the teacher has moved to a transfer task in the same domain.
                for future_n, future in enumerate(rounds[n:], n+1):
                    if not same_domain(future_n):
                        break
                    future_evidence = future.get('evidence') or {}
                    if not future.get('_learning_evidence_allowed', True):
                        continue
                    if future_evidence.get('shows_residual_misconception'):
                        break
                    if future_evidence.get('explains_reason_correctly') and not any(future_evidence.get(key) for key in ('parrots_teacher', 'conceptual_uncertainty', 'evidence_insufficient')):
                        if checks['misconception_diagnosis'][2] < 1:
                            checks['misconception_diagnosis'][2] = 1.
                            citations['misconception_diagnosis'][2] = [future_n]
                            citation_roles['misconception_diagnosis'][2] = {
                                'teacher_rounds': [future_n],
                                'student_rounds': [future_n],
                            }
                        break
            if action in {'example', 'guided_question', 'correction', 'direct_answer'} or task:
                scaffold = not direct and any(word in text for word in ('先', '固定', '比较', '代入', '相乘', '交叉', '展开', '观察', '画'))
                participates = response_learning_allowed and not direct and not current_evidence.get('parrots_teacher') and current_evidence.get('evidence_level', 0) > 0
                record(
                    'scaffolding',
                    [1 if scaffold else 0, 1 if participates else 0, 1 if not direct and independent and (reason or current_evidence.get('transfer_success')) else .5 if not direct and independent else 0],
                    teacher_rounds=[[n], [], [n]],
                    student_rounds=[[], [n], [n]],
                )
        if task_claims:
            known.extend(truth for _, truth in task_claims)
        for name in opportunities:
            samples[name].append(sum(checks[name]) / 3 * 100)
            def check_reason(i):
                status = ['未观察到满足该项的证据', '观察到部分证据', '观察到明确证据'][int(checks[name][i]*2)]
                roles = citation_roles[name][i]
                excerpts = []
                if roles['teacher_rounds']:
                    teacher_round = roles['teacher_rounds'][0]
                    excerpts.append(f'教师第{teacher_round}轮：{rounds[teacher_round-1]["teacher_text"][:100]}')
                if roles['student_rounds']:
                    student_round = roles['student_rounds'][0]
                    excerpts.append(f'学生第{student_round}轮：{rounds[student_round-1]["student_text"][:100]}')
                return status + (('；' + '；'.join(excerpts)) if excerpts else '')
            evidence['dimensions'].setdefault(name, []).append({
                'task': identity,
                'checks': [{
                    'criterion': label,
                    'value': checks[name][i],
                    'rounds': citations[name][i],
                    'teacher_rounds': citation_roles[name][i]['teacher_rounds'],
                    'student_rounds': citation_roles[name][i]['student_rounds'],
                    'reason': check_reason(i),
                } for i, label in enumerate(CHECKS[name])],
            })
    scores = {name: round(sum(samples[name])/len(samples[name]), 2) if samples[name] else None for name in CHECKS}
    scores['knowledge_accuracy'] = round(sum(known)/len(known)*100, 2) if known else None
    coverage = sum(weight for name, weight in WEIGHTS.items() if scores[name] is not None)
    evidence['coverage'] = round(coverage, 2)
    scores['overall_score'] = round(sum((scores[name] or 0)*weight for name, weight in WEIGHTS.items()) / coverage, 2) if len(groups) >= 3 and scores['knowledge_accuracy'] is not None and coverage >= .8 else None
    return scores, evidence
