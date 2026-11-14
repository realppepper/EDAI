"""Optional all-MOS anti-windup candidate; frozen model coefficients retained."""
def overload_clamp_candidate(baseline_text,bleed_resistance=10e6):
    marker='.ends FIRSTAMP'
    if baseline_text.count(marker)!=1 or 'Maw1' in baseline_text:raise ValueError('Unexpected source circuit')
    if not 0<bleed_resistance<1e12:raise ValueError('Invalid off-state resistance')
    clamp=f'''* Three diode-connected PMOS devices limit deep second-stage gate windup
Maw1 AW1 AW1 VP VP GPM W=100u L=2u
Maw2 AW2 AW2 AW1 VP GPM W=100u L=2u
Maw3 X X AW2 VP GPM W=100u L=2u
* Weak off-state paths define intermediate nodes without forced initial states
Raw1 VP AW1 {bleed_resistance:.12g}
Raw2 AW1 AW2 {bleed_resistance:.12g}
Raw3 AW2 X {bleed_resistance:.12g}
'''
    return baseline_text.replace(marker,clamp+marker)
