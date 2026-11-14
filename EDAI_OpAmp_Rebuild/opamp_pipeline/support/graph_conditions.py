"""Annotate overrides, sweeps and trace conditions; do not generate fixtures."""
from copy import deepcopy
import re


def graph_condition_annotations(metadata):
    source=metadata.get('conditions',{})
    common=source.get('original_common_conditions',{})
    raw=source.get('local_overrides',{})
    local={};supersedes={};invalidated={};trace_conditions=[];printed={}
    aliases={'load_connection':'load_connected_to','load_resistance':'load_resistance_Ohm'}
    for field,value in raw.items():
        if field.endswith('_printed'):
            printed[field]=deepcopy(value)
            continue
        target=aliases.get(field,field)
        if field=='load_resistance' and value=='open':value={'kind':'open_circuit'}
        if field=='supply_voltage_V_range':
            target='supply_voltage_V';value={'min':value[0],'max':value[1]}
        if target in local and local[target]!=value:raise ValueError('Conflicting graph condition aliases')
        local[target]=deepcopy(value)
        if target in common:supersedes[target]={'by':'local_overrides.'+field}
    swept=source.get('swept_quantity','').casefold()
    sweep_fields=[]
    for phrase,field in [('supply voltage','supply_voltage_V'),('temperature','ambient_temperature_C'),
                          ('temp(','ambient_temperature_C'),('common-mode voltage','input_common_mode_expression'),
                          ('frequency','frequency_Hz'),('output current','output_current_A'),
                          ('capacitance','load_capacitance_F'),('amplitude','output_amplitude_Vpp'),('time','time_s')]:
        if phrase in swept:
            sweep_fields.append(field)
            if field in common:invalidated[field]='Axis sweep replaces the common fixed condition'
    if 'supply_voltage_V' in local or 'supply_voltage_V' in sweep_fields:
        if 'rails_V' in common:invalidated['rails_V']='Local/swept supply does not establish the common fixed rail voltages'
    temperature=metadata.get('temperature',{})
    if temperature.get('kind') in {'sweep','series'} and 'ambient_temperature_C' in common:
        invalidated['ambient_temperature_C']='Temperature varies by axis or trace; common temperature is not fixed for all data'
    for index,trace in enumerate(metadata.get('traces',[])):
        values={};drops=[]
        if 'temperature_C' in trace:values['ambient_temperature_C']=trace['temperature_C']
        label=trace.get('label','')
        supply=re.fullmatch(r'VS\s*=\s*([0-9.]+)\s*V',label,re.I)
        resistance=re.fullmatch(r'RL\s*=\s*([0-9.]+)(k|M)?Ohm',label)
        if supply:
            values['supply_voltage_V']=float(supply.group(1));drops.append('rails_V')
        if resistance:
            values['load_resistance_Ohm']=float(resistance.group(1))*{'k':1e3,'M':1e6,None:1}[resistance.group(2)]
        if values:trace_conditions.append({'trace_index':index,'label':label,'overrides':values,
                                           'supersedes_common_fields':list(values),'invalidated_common_fields':drops})
    if source.get('local_overrides',{}).get('load_series_Ohm'):
        if 'load_resistance_Ohm' in common:invalidated['load_resistance_Ohm']='Load resistance is selected per trace, not fixed at the common value'
    return {'local_conditions_canonical':local,'supersedes_common_fields':supersedes,
        'invalidated_common_fields':invalidated,'swept_fields':sweep_fields,'trace_conditions':trace_conditions,
        'unresolved_printed_annotations':printed,
        'voltage_reference':'Keep source rail-relative/midpoint expressions; do not interpret VS/2 as absolute ground voltage without a fixture.',
        'effective_conditions_generated':False,'source_conditions_modified':False}
