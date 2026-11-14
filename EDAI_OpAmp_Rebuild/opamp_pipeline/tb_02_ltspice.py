"""Run isolated batch jobs and read explicit .meas scalars. Never reuse old logs."""
import math,re,subprocess
from pathlib import Path

def decode_log(path):
    data=Path(path).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8',errors='replace')

def parse_measurements(text,names):
    result={}
    for name in names:
        # LTspice WHEN-only measurement prints "expression=threshold AT coordinate".
        # FIND prints a value followed by lowercase "at". The threshold is not the result.
        number=r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
        events=re.findall(rf'^\s*{re.escape(name)}\s*:[^\r\n]*?=\s*{number}\s+AT\s+({number})\s*$',text,re.M)
        if len(events)==1:
            value=float(events[0])
            if math.isfinite(value):result[name]=value
            continue
        pattern=rf'^\s*{re.escape(name)}\s*:(?:[^\r\n]*?)=\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(?:$|at\b|from\b)'
        # AC scalar expressions are logged as Cartesian (real, imaginary).
        number=r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
        complex_hits=re.findall(rf'^\s*{re.escape(name)}\s*:[^\r\n]*?=\s*\(\s*({number})\s*,\s*({number})\s*\)\s+at\b',text,re.M|re.I)
        if len(complex_hits)==1 and float(complex_hits[0][1])==0:
            value=float(complex_hits[0][0])
            if math.isfinite(value):result[name]=value
            continue
        hits=re.findall(pattern,text,re.M|re.I)
        if len(hits)==1:
            value=float(hits[0])
            if math.isfinite(value):result[name]=value
    return result

def run_bench(executable,netlist,names,ascii_raw=False,timeout=45):
    netlist=Path(netlist).resolve();log=netlist.with_suffix('.log')
    if log.exists():raise ValueError('Refusing existing log; choose a new run directory')
    command=[str(executable),'-b']+(['-ascii'] if ascii_raw else [])+[str(netlist)]
    proc=subprocess.run(command,cwd=netlist.parent,capture_output=True,timeout=timeout,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if proc.returncode!=0:
        text=decode_log(log) if log.exists() else ''
        reasons=[line.strip() for line in text.splitlines() if re.search(r'error|unknown|fatal|cannot|not found|syntax|no such',line,re.I)]
        raise RuntimeError(f'LTspice exited {proc.returncode}; log={log}; '+(' | '.join(reasons) or 'See full saved log'))
    if not log.exists():raise RuntimeError('LTspice did not create a log')
    text=decode_log(log)
    values=parse_measurements(text,names)
    if set(values)!=set(names):raise RuntimeError(f'Missing/failed measurements: {set(names)-set(values)}; see {log}')
    return {'measurements':values,'log':str(log),'returncode':proc.returncode}
