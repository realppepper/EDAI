"""Keep model limitations, missing adapters and non-applicable tests distinct."""


def measurement_capability(symbol,model_capabilities,channels=1):
    required={
        'RID':('calibrated_gate_leakage','Scalar input resistance needs validated finite gate leakage.'),
        'EN_RMS':('calibrated_noise','Integrated RMS voltage noise needs calibrated thermal and flicker noise.'),
        'in':('calibrated_input_current_noise','Input current noise requires a validated input-current noise model.'),
        'EMIRR':('calibrated_rf_rectification','EMI rejection requires validated RF coupling and rectification.'),
        'THD+N':('calibrated_noise','THD+N cannot be qualified from deterministic distortion and uncalibrated noise.'),
        'IB':('calibrated_gate_leakage','Ideal gate current is not validated bias current.'),
        'IOS':('calibrated_gate_leakage','Input leakage mismatch is not calibrated.'),
        'en':('calibrated_noise','Thermal-only noise is not calibrated full voltage-noise density.')}
    if symbol=='Channel separation, dc' and channels<2:
        return {'status':'not_applicable','measurement_attempted':False,'passed':False,
                'reason':'One physical channel has no aggressor/victim channel pair.'}
    if symbol in required:
        key,reason=required[symbol]
        if model_capabilities.get(key) is not True:
            return {'status':'unverified_model','measurement_attempted':False,'passed':False,
                    'required_model_capability':key,'reason':reason}
    if symbol in {'RID','ts'}:
        return {'status':'adapter_available','passed':False,'reason':'Source conditions and reference qualification still required.'}
    return {'status':'unverified_adapter','measurement_attempted':False,'passed':False,
            'reason':'Model capability alone does not establish a qualified measurement adapter.'}
