"""Manual chat designer contract; a future API can produce the same response."""
import json,re,math
from pathlib import Path
from .design_01_cmos_candidate import MODELS
from .support.source_checks import fingerprint
from .support.execution_state import file_hash
from .ref_03_design_context import make_prompt
from .support.atomic_files import atomic_write_text


def write_json(path,value):
    text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)
    atomic_write_text(path,text)


def validate_dut(text):
    if not isinstance(text,str) or not text.startswith(MODELS):raise ValueError('Frozen generic models must be preserved verbatim')
    body=[s.strip() for s in text[len(MODELS):].splitlines() if s.strip() and not s.lstrip().startswith('*')]
    if not body or body[0].upper()!='.SUBCKT FIRSTAMP P N VP VM OUT' or body[-1].upper()!='.ENDS FIRSTAMP':
        raise ValueError('Explicit current DUT interface required')
    def number(token):
        m=re.fullmatch(r'([-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)(meg|[tgkmunpf])?',token,re.I)
        if not m:raise ValueError('Current adapter requires numeric element values and W/L')
        scales={'':1,'t':1e12,'g':1e9,'meg':1e6,'k':1e3,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15}
        value=float(m[1])*scales[(m[2] or '').lower()]
        if not math.isfinite(value):raise ValueError('Nonfinite component value')
        return value
    seen=set()
    for line in body[1:-1]:
        if line[0].upper() not in 'MRC' or re.search(r'\b(?:nan|inf|infinity)\b',line,re.I):
            raise ValueError('Current topology adapter accepts MOS/resistor/capacitor lines only')
        tokens=line.split();name=tokens[0].upper()
        if name in seen:raise ValueError('Duplicate component name')
        seen.add(name)
        if name[0] in 'RC':
            if len(tokens)!=4:raise ValueError('Invalid passive component')
            value=number(tokens[3])
            if value<0 or (name[0]=='C' and value==0):raise ValueError('Nonphysical passive value')
        else:
            if len(tokens)<8 or tokens[5].upper() not in {'GNM','GPM'}:raise ValueError('Frozen MOS type and explicit geometry required')
            dimensions=dict(token.upper().split('=',1) for token in tokens[6:])
            if set(dimensions)!={'W','L'} or any(number(v)<=0 for v in dimensions.values()):raise ValueError('Positive MOS W/L required')
    return True


def prepare_request(session,state):
    session=Path(session);index=len(state['candidates'])
    current=state['candidates'][-1];context=json.loads((session/'CONTEXT.json').read_text(encoding='utf-8'))
    best=next(c for c in state['candidates'] if c['id']==state['best_candidate_id'])
    compact=make_prompt(context)
    for row in compact['required_rows']:
        if 'condition_details_location' in row:row['condition_details_location']='CONTEXT.json required_rows[].cases; not waived'
    request={'schema_version':1,'request_id':fingerprint([state['session_id'],index,current['candidate_sha256'],state['policy_fingerprint']]),
        'designer':'current_chat_assistant','task':'Propose a full modified transistor netlist; physical cause is a hypothesis until experimentally checked.',
        'active_policy':state['policy'],'feedback':current['assessment'],
        'latest_candidate_netlist':Path(current['candidate_path']).read_text(encoding='utf-8'),
        'best_candidate':state['best_candidate_id'],'best_candidate_assessment':best['assessment'],
        'best_candidate_netlist':Path(best['candidate_path']).read_text(encoding='utf-8'),
        'all_required_targets':compact['required_rows'],'full_condition_details':'CONTEXT.json',
        'reference_papers':context['reference_papers'],'reference_rules':context['reference_rules'],
        'constraints':['Do not change model parameters, testbenches, source targets or active trial policy.',
                       'Current adapter uses FIRSTAMP P N VP VM OUT and the existing internal bias node names.',
                       'An abstract is not evidence of a circuit equation or exact device value.',
                       'Report unknown chat token usage as null, never zero.'],
        'response_fields':['request_id','based_on_request_sha256','author','netlist','reasoning','reference_ids','token_usage'],
        'external_llm_api_calls':0}
    path=session/f'DESIGN_REQUEST_{index:03d}.json'
    write_json(path,request)
    state['pending_request']={'path':str(path),'sha256':file_hash(path),'request_id':request['request_id']}
    state['status']='awaiting_chat_design'


def accept_response(session,state,response_path):
    pending=state.get('pending_request')
    if state['status']!='awaiting_chat_design' or not pending:raise ValueError('No pending design request')
    if file_hash(pending['path'])!=pending['sha256']:raise ValueError('Request was modified')
    response=json.loads(Path(response_path).read_text(encoding='utf-8'))
    if response.get('request_id')!=pending['request_id'] or response.get('based_on_request_sha256')!=pending['sha256']:
        raise ValueError('Response is not bound to the current request')
    if response.get('author')!='current_chat_assistant':raise ValueError('Current mode requires a declared chat designer')
    if not isinstance(response.get('reasoning'),dict) or not response['reasoning']:raise ValueError('Design reasoning required')
    if response.get('token_usage') is not None:raise ValueError('Manual chat token usage is unobserved in this bridge; must be null')
    context=json.loads((Path(session)/'CONTEXT.json').read_text(encoding='utf-8'))
    ids={p['id'] for p in context['reference_papers']}
    if not set(response.get('reference_ids',[]))<=ids:raise ValueError('Unknown literature reference')
    validate_dut(response['netlist'])
    folder=Path(session)/f"candidate_{len(state['candidates']):03d}"
    if folder.exists():
        # An interruption between preparing files and saving STATE may leave an orphan.
        # Identical complete preparation is safely reused; different contents stay intact.
        receipt=folder/'DESIGN_RESPONSE.json';netlist=folder/'candidate.inc'
        identical=(receipt.exists() and netlist.exists() and
                   json.loads(receipt.read_text(encoding='utf-8'))==response and
                   netlist.read_text(encoding='ascii')==response['netlist'])
        if not identical:
            for retry in range(1,11):
                alternative=folder.with_name(folder.name+f'_prepare_retry_{retry:02d}')
                if not alternative.exists():folder=alternative;break
            else:raise ValueError('Too many orphan preparations; inspect session')
    folder.mkdir(exist_ok=True)
    if not (folder/'DESIGN_RESPONSE.json').exists():write_json(folder/'DESIGN_RESPONSE.json',response)
    if not (folder/'candidate.inc').exists():(folder/'candidate.inc').write_text(response['netlist'],encoding='ascii')
    state['pending_candidate']={'id':folder.name,'folder':str(folder),'candidate_path':str(folder/'candidate.inc'),
        'candidate_sha256':file_hash(folder/'candidate.inc'),'response_sha256':file_hash(folder/'DESIGN_RESPONSE.json'),
        'based_on_request_sha256':pending['sha256'],'execution_attempts':[],'token_usage':None}
    state['status']='testing_candidate';state['pending_request']=None
