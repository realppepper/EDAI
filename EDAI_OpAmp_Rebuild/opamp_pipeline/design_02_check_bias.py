"""Nominal LEVEL1 headroom diagnostic, not a temperature-corrected device OP oracle."""
import math


def region(vgs,vds,threshold):
    overdrive=vgs-threshold
    state='cutoff' if overdrive<=0 else ('saturation' if vds>=overdrive else 'linear')
    return {'vgs_magnitude_V':vgs,'vds_magnitude_V':vds,'threshold_nominal_V':threshold,
            'overdrive_V':overdrive,'saturation_margin_V':vds-overdrive,'region_nominal':state}


def check_bias(snapshot):
    def node(name):return snapshot['v('+name+')'] if name!='0' else 0.0
    devices=[('Mref','xdut:bias','xdut:bias','0','n'),
             ('Mtail','xdut:tail','xdut:bias','0','n'),
             ('M1','xdut:diode','inn','xdut:tail','n'),
             ('M2','xdut:x','inp','xdut:tail','n'),
             ('M3','xdut:diode','xdut:diode','vp','p'),
             ('M4','xdut:x','xdut:diode','vp','p'),
             ('M5','out','xdut:x','vp','p'),('M6','out','xdut:bias','0','n')]
    result=[]
    for name,d,g,s,kind in devices:
        if kind=='n':
            threshold=.65+.4*(math.sqrt(.7+max(node(s),0))-math.sqrt(.7))
            metrics=region(node(g)-node(s),node(d)-node(s),threshold)
        else:metrics=region(node(s)-node(g),node(s)-node(d),.7)
        result.append({'device':name,**metrics})
    return {'method':'nominal LEVEL1 thresholds with NMOS body effect; not exact LTspice temperature-adjusted VDSAT',
            'scope':'5V quiescent point only; saturation is not a universal requirement for every transient state',
            'devices':result,'all_eight_conducting_and_saturated_nominal':all(x['region_nominal']=='saturation' for x in result)}
