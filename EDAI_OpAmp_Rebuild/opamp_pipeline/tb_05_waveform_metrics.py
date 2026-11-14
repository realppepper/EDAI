"""Read LTspice ASCII real raw data and measure finite-window settling safely."""
import math
from .tb_02_ltspice import decode_log


def read_real_raw(path):
    text=decode_log(path)
    if 'Flags: real' not in text or 'Values:' not in text:
        raise ValueError('Expected uncompressed ASCII real raw data')
    header,body=text.split('Values:',1)
    count=int(next(s.split(':',1)[1] for s in header.splitlines() if s.startswith('No. Points:')))
    variables=header.split('\nVariables:',1)[1].strip().splitlines()
    names=[s.split()[1].lower() for s in variables]
    if len(names)!=len(set(names)):raise ValueError('Duplicate raw variable')
    tokens=body.split();width=len(names)+1
    if len(tokens)!=count*width:raise ValueError('Truncated or unexpected raw samples')
    columns={name:[] for name in names}
    for i in range(count):
        row=tokens[i*width:(i+1)*width]
        if int(row[0])!=i:raise ValueError('Unexpected raw point index')
        for name,value in zip(names,row[1:]):
            number=float(value)
            if not math.isfinite(number):raise ValueError('Nonfinite waveform')
            columns[name].append(number)
    return columns


def settling_metrics(time,output,step):
    if len(time)!=len(output) or len(time)<2:raise ValueError('Invalid waveform lengths')
    if any(not math.isfinite(x) for x in [*time,*output]):raise ValueError('Nonfinite waveform')
    if any(b<=a for a,b in zip(time,time[1:])):raise ValueError('Time must increase strictly')
    end=step['start_s']+step['transition_s'];target=step['final_V']
    amplitude=abs(target-step['initial_V']);band=amplitude*step['error_fraction']
    if amplitude<=0 or band<=0:raise ValueError('Step and tolerance must be positive')
    if time[0]>end or time[-1]<step['stop_s']-step['max_step_s']:
        raise ValueError('Incomplete observation window')
    indices=[i for i,t in enumerate(time) if t>=end]
    outside=[i for i in indices if abs(output[i]-target)>band]
    settled=bool(indices) and (not outside or outside[-1]<len(time)-1)
    if outside and outside[-1]==len(time)-1:
        return {'status':'not_settled_in_observation_window','settling_s':None,'band_V':band,
                'observed_until_s':time[-1],'final_error_V':output[-1]-target}
    crossing=end
    if outside:
        i=outside[-1];j=i+1
        boundary=target+(band if output[i]>target else -band)
        crossing=time[i]+(boundary-output[i])*(time[j]-time[i])/(output[j]-output[i])
    sign=1 if target>step['initial_V'] else -1
    overshoot=max(0,max(sign*(output[i]-target) for i in indices))/amplitude*100
    return {'status':'settled_within_observation_window' if settled else 'invalid',
            'settling_s':max(0,crossing-end),'band_V':band,'overshoot_percent':overshoot,
            'final_error_V':output[-1]-target,'observed_until_s':time[-1],
            'observation_only_not_infinite_time_guarantee':True}
