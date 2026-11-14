"""Validate source interpretation annotations without building effective fixtures."""


def validate_condition_annotations(conditions, condition_sets):
    common=condition_sets.get(conditions.get('inherits'),{})
    overrides=conditions.get('overrides',{})
    replacements=conditions.get('inheritance_replacements',{})
    roles=conditions.get('quantity_roles',{})
    issues=[]
    if not isinstance(replacements,dict) or not isinstance(roles,dict):
        return ['Condition interpretation annotations must be objects']
    for inherited_field,local_field in replacements.items():
        if inherited_field not in common:
            issues.append('Replacement refers to absent inherited field: '+inherited_field)
        if not isinstance(local_field,str) or local_field not in overrides:
            issues.append('Replacement must refer to an explicit local condition')
    for field,role in roles.items():
        if field not in common and field not in overrides:
            issues.append('Quantity role refers to absent condition: '+field)
        if role not in {'dc_bias','ac_rms_amplitude','sweep_range','explicit_dc_voltage'}:
            issues.append('Unsupported quantity role: '+str(role))
    for default_field,local_field in [('input_common_mode_expression','input_common_mode_V'),
                                      ('output_voltage_expression','output_voltage_V')]:
        if default_field in common and local_field in overrides and replacements.get(default_field)!=local_field:
            issues.append('Local range/value needs an explicit inherited-expression replacement: '+local_field)
    if 'output_voltage_expression' in common and 'output_voltage_Vrms' in overrides:
        if roles.get('output_voltage_expression')!='dc_bias' or roles.get('output_voltage_Vrms')!='ac_rms_amplitude':
            issues.append('Output DC bias and AC RMS amplitude roles must be explicit')
    resistance=overrides.get('load_resistance_Ohm')
    if isinstance(resistance,dict) and 'connected_to' in resistance and 'load_connected_to' in overrides:
        if resistance['connected_to']!=overrides['load_connected_to']:
            issues.append('Nested and explicit load connection overrides disagree')
    return issues
