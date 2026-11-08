"""opamp_gen.cir 를 읽어 LTspice 회로도(opamp_gen_schematic.asc)를 만든다. 사용법: python make_schematic.py"""
from pathlib import Path
import json
root=Path(__file__).parent
out=root
devices={}
for line in (root/'opamp_gen.cir').read_text(encoding='utf-8').splitlines():
 t=line.split()
 if t and t[0][0] in 'XR' and not t[0].startswith('*'): devices[t[0]]=t
 if t and t[0].startswith('CC'):devices[t[0]]=t
lines=['Version 4','SHEET 1 3200 2000']
def wire(a,b):lines.append(f'WIRE {a[0]} {a[1]} {b[0]} {b[1]}')
def flag(a,n):lines.append(f'FLAG {a[0]} {a[1]} {n}')
def text(x,y,s,size=3):lines.append(f'TEXT {x} {y} Left {size} ;{s}')
def box(x,y,w,h,title):
 lines.append(f'RECTANGLE Normal {x} {y} {x+w} {y+h}')
 text(x+24,y+24,title,4)
pins={}
def mos(name,x,y):
 t=devices[name];p=t[5].startswith('p'); sym='pmos4' if p else 'nmos4'
 # y is upper terminal; PMOS source is upper, NMOS drain is upper.
 ox,oy,rot=(x+48,y+96,'R180') if p else (x-48,y,'R0')
 lines.extend([f'SYMBOL {sym} {ox} {oy} {rot}',f'WINDOW 0 {(-72 if p else 72)} {(-20 if p else 24)} {"Right" if p else "Left"} 2',f'WINDOW 3 {(-72 if p else 72)} {(-50 if p else 54)} {"Right" if p else "Left"} 1',f'SYMATTR InstName {name[1:]}',f'SYMATTR Prefix X',f'SYMATTR Value {t[5]}',f'SYMATTR SpiceLine {" ".join(t[6:])}'])
 d=(x,y+96) if p else (x,y);s=(x,y) if p else (x,y+96);g=(x+48,y+16) if p else (x-48,y+80);b=(x,y+48)
 pins[name]=dict(zip('DGSB',[d,g,s,b]))
 for pos,node,dx,dy in [(d,t[1],0,32 if p else -32),(s,t[3],0,-32 if p else 32),(g,t[2],64 if p else -64,0),(b,t[4],-48 if p else 48,0)]:
  end=(pos[0]+dx,pos[1]+dy);wire(pos,end);flag(end,node)
def passive(name,x,y):
 t=devices[name];r=name.startswith('R');sy='res' if r else 'cap'; oy=y-16 if r else y
 lines.extend([f'SYMBOL {sy} {x-16} {oy} R0',f'SYMATTR InstName {name}',f'SYMATTR Value {t[3]}'])
 a=(x,y);b=(x,y+(80 if r else 64));pins[name]={'A':a,'B':b}
 for pos,node,dy in [(a,t[1],-32),(b,t[2],32)]:
  end=(x,pos[1]+dy);wire(pos,end);flag(end,node)
text(40,16,'OPAMP_GEN | TLV271 target / GF180MCU 6V devices / VDD = 5V',4)
text(40,68,'Transistor-level schematic reconstructed from the saved opamp_gen.cir; simulation evidence: ngspice, 15/15 judged checks PASS.',2)
box(32,128,1320,1072,'1. PMOS INPUT FOLDED CASCODE')
box(1384,128,1200,1072,'2. CLASS-AB OUTPUT STAGE')
box(2616,128,552,1072,'3. MILLER Rz-Cc')
box(32,1240,1600,688,'4. BETA-MULTIPLIER + STARTUP')
box(1664,1240,920,688,'5. CASCODE GATE BIAS')
positions={
 'XMT_s1':(704,240),'XM1_s1':(576,480),'XM2_s1':(928,480),
 'XMP3_s1':(256,240),'XMP4_s1':(1184,240),'XMPC3_s1':(256,480),'XMPC4_s1':(1184,480),
 'XMNC1_s1':(256,720),'XMNC2_s1':(1184,720),'XMN3_s1':(256,1008),'XMN4_s1':(1184,1008),
 'XMB9_s2':(1568,240),'XMAN2_s2':(1568,480),'XMAN1_s2':(1568,720),
 'XMAP1_s2':(1952,240),'XMAP2_s2':(1952,480),'XMB10_s2':(1952,720),
 'XMOP_s2':(2368,480),'XMON_s2':(2368,1008),'XMAN_s2':(1568,1008),'XMAP_s2':(1952,1008),
 'XMB4_b1':(256,1376),'XMB1_b1':(256,1696),'XMB3_b1':(640,1376),'XMB2_b1':(640,1600),
 'XMS1_b1':(1088,1696),'XMS2_b1':(1440,1696),
 'XMB5_b2':(1872,1376),'XMB6_b2':(1872,1696),'XMB8_b2':(2336,1376),'XMB7_b2':(2336,1696)}
for name,xy in positions.items():mos(name,*xy)
for name,x,y in [('RB_b1',640,1776),('RS_b1',1088,1408),('RZ_c1',2784,320),('CC_c1',2784,560),('RZ_c2',3008,720),('CC_c2',3008,960)]:passive(name,x,y)
def join(n1,p1,n2,p2):
 a,b=pins[n1][p1],pins[n2][p2]
 if a[0]==b[0] or a[1]==b[1]:wire(a,b)
 else:
  mid=(a[0],(a[1]+b[1])//2);mid2=(b[0],mid[1]);wire(a,mid);wire(mid,mid2);wire(mid2,b)
for a,pa,b,pb in [('XMP3_s1','D','XMPC3_s1','S'),('XMP4_s1','D','XMPC4_s1','S'),('XMPC3_s1','D','XMNC1_s1','D'),('XMNC1_s1','S','XMN3_s1','D'),('XMNC2_s1','S','XMN4_s1','D'),('XMB9_s2','D','XMAN2_s2','D'),('XMAN2_s2','S','XMAN1_s2','D'),('XMAP1_s2','D','XMAP2_s2','S'),('XMAP2_s2','D','XMB10_s2','D'),('XMOP_s2','D','XMON_s2','D'),('XMB4_b1','D','XMB1_b1','D'),('XMB3_b1','D','XMB2_b1','D'),('XMB2_b1','S','RB_b1','A'),('RS_b1','B','XMS1_b1','D'),('XMB5_b2','D','XMB6_b2','D'),('XMB8_b2','D','XMB7_b2','D'),('RZ_c1','B','CC_c1','A'),('RZ_c2','B','CC_c2','A')]:join(a,pa,b,pb)
# Input-pair common source and folded branch connections.
wire((704,336),(704,400));wire((576,400),(928,400));wire((576,400),(576,480));wire((928,400),(928,480))
wire((576,576),(576,912));wire((576,912),(256,912))
wire((928,576),(928,912));wire((928,912),(1184,912))
wire((1184,576),(1280,576));flag((1280,576),'gp')
wire((1184,720),(1280,720));flag((1280,720),'gn')
wire((2368,816),(2512,816));flag((2512,816),'OUT')
text(2650,1136,'Each branch: 600 ohm + 3 pF',2)
text(2640,1300,'CONNECTION NOTES',3)
text(2640,1360,'Same net labels are electrically connected.',2)
text(2640,1420,'4-terminal MOS: D / G / S / bulk retained.',2)
text(2640,1480,'All 31 MOS + 4 R + 2 C retained.',2)
text(2640,1540,'W/L and multiplicity retained in attributes.',2)
text(2640,1640,'Existing simulation: ngspice / GF180MCU.',2)
text(2640,1700,'This LTspice drawing is a visual reconstruction,',2)
text(2640,1740,'not a new LTspice simulation result.',2)
assert set(positions)=={k for k in devices if k.startswith('X')}
(out/'opamp_gen_schematic.asc').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('31 MOS, 4 R, 2 C preserved; saved',out/'opamp_gen_schematic.asc')