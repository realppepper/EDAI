"""Attach selected literature to an awaiting request, retaining frozen prior requests."""
from pathlib import Path
from .ref_05_research import load_supplement,enrich_request
from .support.execution_state import file_hash
from .loop_02_handoff import write_json


def attach(session,supplement_path,kind='fixed'):
    session=Path(session).resolve();supplement_path=Path(supplement_path).resolve()
    if kind=='initial':
        from . import startup_02_datasheet as control
        state=control.load(session)
        if state['status']!='awaiting_initial_design':raise ValueError('Initial design request is not awaiting a designer')
    else:
        from . import harness_03_loop as control
        state=control.load(session)
        if state['status']!='awaiting_chat_designer':raise ValueError('Fixed-loop design request is not awaiting a designer')
    pending=state['pending_request'];old=Path(pending['path'])
    if file_hash(old)!=pending['sha256']:raise ValueError('Pending request changed')
    supplement,request=load_supplement(supplement_path,old)
    if request.get('literature_reference'):raise ValueError('Already attached; use a new design request')
    index=len(state.get('literature_request_history',[]))+1
    new=old.with_name(old.stem+f'_literature_{index:03d}.json');enriched=enrich_request(request,supplement)
    if new.exists():raise ValueError('Reference request version already exists')
    write_json(new,enriched)
    artifacts={str(supplement_path):file_hash(supplement_path),**supplement['artifacts'],str(old):file_hash(old)}
    state.setdefault('literature_artifacts',{}).update(artifacts)
    state.setdefault('literature_request_history',[]).append({'prior_request':dict(pending),'supplement':str(supplement_path),
        'new_request':str(new),'body_excerpt_characters':supplement['body_excerpt_characters'],
        'design_usage':'not_yet_reported','design_candidate_budget_consumed':0})
    state['pending_request']={'path':str(new),'sha256':file_hash(new),'request_id':enriched['request_id']}
    if kind=='initial':control._save(session,state)
    else:control.save(session,state)
    return state
