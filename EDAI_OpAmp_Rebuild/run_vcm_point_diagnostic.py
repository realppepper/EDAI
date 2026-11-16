"""Inspect missing points of three saved candidates without rewriting their results."""
import json, time, re
from pathlib import Path
from collections import Counter
from opamp_pipeline.diag_04_vcm_points import point_deck, assess_point
from opamp_pipeline.tb_02_ltspice import run_bench, decode_log
from opamp_pipeline.tb_05_waveform_metrics import read_real_raw
from opamp_pipeline.loop_04_extended_policy import ledger
from opamp_pipeline.support.execution_state import file_hash
from opamp_pipeline.support.atomic_files import atomic_write_text, atomic_write_bytes

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'runs/harness_comparison/20261115_feedback_v2_repeats'
OUT = ROOT/'runs/diagnostics/20261115_missing_vcm_points'
EXE = Path('C:/Users/wowyo/AppData/Local/Programs/ADI/LTspice/LTspice.exe')
CASE = 'CASE-578503d6c638ff551bcc'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, data):
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'STATE.json').exists():
        return read(OUT/'STATE.json')
    signatures = {str(p): file_hash(p) for p in [Path(__file__), ROOT/'opamp_pipeline/diag_04_vcm_points.py',
                  ROOT/'opamp_pipeline/tb_02_ltspice.py', ROOT/'opamp_pipeline/tb_05_waveform_metrics.py']}
    groups = []
    for pair, cell in [('pair_02','cell_01'), ('pair_02','cell_02'), ('pair_03','cell_02')]:
        folder = SOURCE/pair/cell
        source_result = folder/'validation/core/execution/RESULT.json'
        result = read(source_result)
        record = ledger(result)[CASE]
        coverage = record['case']['measurement_coverage']
        if coverage['expected_points'] != 201 or coverage['missing_count'] != 8:
            raise ValueError('Source missing-point contract changed')
        matches = []
        for job in result['job_cache'].values():
            if job.get('label') != 'VCM_default':
                continue
            path = Path(job['path'])
            text = path.read_text(encoding='ascii')
            if re.search(r'^VDD vp 0 15$', text, re.M):
                matches.append((path, text))
        if len(matches) != 1:
            raise ValueError('Expected one saved full ascending15V sweep')
        path, text = matches[0]
        name = pair+'_'+cell
        dest = OUT/name
        dest.mkdir()
        model = dest/'candidate.inc'
        original_model = folder/'candidate.inc'
        atomic_write_bytes(model, original_model.read_bytes())
        for p in (source_result, original_model, path, path.with_suffix('.raw'), path.with_suffix('.log'), model):
            signatures[str(p)] = file_hash(p)
        rule = record['target']['rules'][1]
        if rule['metric'] != 'unity_tracking_abs_error' or rule['operator'] != '<=':
            raise ValueError('Unknown tracking acceptance rule')
        points = [{'input_V': value, 'role': 'missing_point'} for value in coverage['missing_samples']]
        points.append({'input_V': 6.75, 'role': 'previously_measured_midpoint_control'})
        jobs = []
        for i, point in enumerate(points):
            for policy in ('original_startup_hint', 'normal_no_hint'):
                job = dest/f'point_{i:02d}'/policy
                job.mkdir(parents=True)
                deck = job/'bench.cir'
                atomic_write_text(deck, point_deck(text, point['input_V'], model, policy))
                signatures[str(deck)] = file_hash(deck)
                jobs.append({**point, 'policy': policy, 'deck': str(deck), 'status': 'pending'})
        groups.append({'name': name, 'source_case': CASE, 'source_result': str(source_result),
                       'tracking_limit_V': rule['value'], 'jobs': jobs})
    state = {'status': 'prepared', 'groups': groups, 'signatures': signatures,
             'planned_jobs': 54, 'new_designs': 0, 'original_ledgers_modified': False,
             'not_a_full_sweep_qualification': True, 'timeout_s': 60}
    save(OUT/'STATE.json', state)
    return state


def main():
    state = prepare()
    if any(file_hash(p) != sha for p, sha in state['signatures'].items()):
        raise ValueError('Frozen source or diagnostic input changed')
    state['status'] = 'running'
    save(OUT/'STATE.json', state)
    for group in state['groups']:
        for job in group['jobs']:
            if job['status'] == 'completed':
                continue
            folder = Path(job['deck']).parent
            attempts = job.setdefault('attempts', [])
            # Fresh folders preserve interrupted attempts and any late logs.
            attempt = folder/f'attempt_{len(attempts)+1:02d}'
            attempt.mkdir()
            deck = attempt/'bench.cir'
            atomic_write_bytes(deck, Path(job['deck']).read_bytes())
            event = {'status': 'started', 'deck': str(deck), 'started_unix': time.time()}
            attempts.append(event)
            save(OUT/'STATE.json', state)
            started = time.monotonic()
            try:
                run_bench(EXE, deck, [], ascii_raw=True, timeout=state['timeout_s'])
                answer = assess_point(read_real_raw(deck.with_suffix('.raw')), job['input_V'], group['tracking_limit_V'])
                log = decode_log(deck.with_suffix('.log'))
                answer['log_operating_point_failure_mentions'] = len(re.findall(r'failed to find (?:the )?operating point', log, re.I))
            except Exception as error:
                answer = {'classification': 'unresolved_execution_or_operating_point',
                          'error_type': type(error).__name__, 'error': str(error),
                          'full_sweep_qualified': False, 'physical_failure_cause_confirmed': False}
            answer['seconds'] = time.monotonic()-started
            save(attempt/'RESULT.json', answer)
            event.update(status='completed', result=str(attempt/'RESULT.json'))
            job.update(status='completed', result=answer)
            save(OUT/'STATE.json', state)
            print(group['name'], job['role'], job['input_V'], job['policy'], answer['classification'], flush=True)
    if any(file_hash(p) != sha for p, sha in state['signatures'].items()):
        raise ValueError('Source/input changed during diagnosis')
    state['status'] = 'completed'
    state['summary'] = {g['name']: dict(Counter(j['result']['classification'] for j in g['jobs'])) for g in state['groups']}
    save(OUT/'STATE.json', state)
    lines = ['# 누락된 VCM 지점 개별 진단', '',
        '원래 회로·전원·부하·오차 기준을 유지하고, DC 스윕 대신 개별 동작점을 계산했다. 각 후보에서 누락8개와 기존 중간값6.75V를 원래 시동 초기 추정값/추정값 없는 일반 계산으로 확인했다. 총54개 계산. 기존 검증 결과를 덮어쓰거나 통과로 변경하지 않는다.', '',
        '| 후보 | 입력(V) | 역할 | 계산 방식 | 결과 | 출력(V) | 오차(V) |',
        '|---|---:|---|---|---|---:|---:|']
    for group in state['groups']:
        for job in group['jobs']:
            r = job['result']
            lines.append(f"|{group['name']}|{job['input_V']:.6g}|{job['role']}|{job['policy']}|{r['classification']}|{r.get('output_V','—')}|{r.get('tracking_error_V','—')}|")
    lines += ['', '개별 동작점의 성공은 원래201점 스윕 전체 통과나 실제 시동·안정성 보장이 아니다. 계산 방식별로 다른 해를 얻으면 민감도 증거이며, 물리적 원인을 확정하지 않는다. 기존 회로·검사 코드·대장은 그대로 보존했다. 상세 값과 로그 경로는STATE.json에 있다.']
    atomic_write_text(OUT/'REPORT.md', '\n'.join(lines)+'\n')
    print(json.dumps(state['summary'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
