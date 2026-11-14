"""Unified qualification pipeline. No designer API calls."""
import argparse,json
from pathlib import Path
from opamp_pipeline.pipeline_01_verification import run_pipeline
from opamp_pipeline.harness_01_fixed import DEFAULT_POLICY


def main():
    p=argparse.ArgumentParser();p.add_argument('--netlist',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--run-dir',type=Path,default=Path('runs/lm358b_overview_20261112'));p.add_argument('--ltspice');p.add_argument('--resume',action='store_true')
    p.add_argument('--harness',type=Path,default=DEFAULT_POLICY);p.add_argument('--import-core',type=Path);p.add_argument('--import-impedance',type=Path);p.add_argument('--import-overload',type=Path);a=p.parse_args()
    imports=[a.import_core,a.import_impedance,a.import_overload]
    if any(imports) and not all(imports):p.error('Import requires all three stages')
    state=run_pipeline(a.netlist,a.run_dir,a.output_dir,a.ltspice,imports if all(imports) else None,a.resume,a.harness)
    print(json.dumps({'status':state['status'],'counts':state['case_status_counts'],'api_calls':0,'output':str(a.output_dir)},ensure_ascii=False))


if __name__=='__main__':main()
