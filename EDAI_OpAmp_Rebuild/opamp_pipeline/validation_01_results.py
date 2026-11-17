"""Common evidence envelope; existing validators still run at their own stages.

An envelope standardizes reporting, not the meaning of individual checks. Unknown
legacy statuses deliberately remain unclassified rather than being called passes.
"""
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = 'verification-result/1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, default=str).encode('utf-8')).hexdigest()


def check_result(check_id, stage, expected, actual, passed, origin, evidence=None):
    return {'check_id': check_id, 'stage': stage, 'status': 'passed' if passed else 'failed',
            'expected': expected, 'actual': actual, 'origin': origin, 'evidence': evidence or {}}


def report(stage, subject, checks, *, status=None, evidence=None, limits=None):
    if status is None:
        status = 'failed' if any(c['status'] == 'failed' for c in checks) else 'passed' if checks else 'not_checked'
    return {'schema_version': SCHEMA_VERSION, 'stage': stage, 'subject': subject,
            'status': status, 'checks': checks, 'evidence': evidence or {}, 'limits': limits or []}


def save_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=str) + '\n'
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def existing_report(path, stage):
    """Read-only envelope for historical output. Keep its native verdict verbatim."""
    path = Path(path)
    raw = path.read_bytes()
    native = json.loads(raw.decode('utf-8-sig'))
    return report(stage, str(path), [], status='native_result_preserved',
                  evidence={'sha256': hashlib.sha256(raw).hexdigest(), 'native_result': native},
                  limits=['No reinterpretation of historical pass/fail or completeness.'])
