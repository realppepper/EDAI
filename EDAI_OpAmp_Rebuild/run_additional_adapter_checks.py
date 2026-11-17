"""Run source-bound supplemental checks without changing a completed workflow."""
import argparse,json
from pathlib import Path
from opamp_pipeline.verify_10_additional import run_additional


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--netlist',type=Path,required=True);p.add_argument('--request',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--ltspice',required=True)
    a=p.parse_args();r=run_additional(a.netlist,a.request,a.output_dir,a.ltspice)
    print(json.dumps({'status':r['status'],'additional_checks_passed':r['all_additional_checks_passed'],
        'cases':[(c['direction'],c['status'],c['measured']['value']) for c in r['additional_cases']]},ensure_ascii=False))


if __name__=='__main__':main()
