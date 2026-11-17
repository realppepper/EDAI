"""Wrap existing stage results in a common read-only evidence index.

Example: --input spec03=path/to/VERIFY.json --input execution=path/to/receipt.json
The original files and their verdicts are never rewritten or converted to passes.
"""
import argparse
from pathlib import Path
from opamp_pipeline.validation_01_results import existing_report, report, save_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',action='append',required=True,metavar='STAGE=JSON_PATH')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    inputs=[]
    for value in args.input:
        stage,separator,path=value.partition('=')
        if not separator or not stage or not path:parser.error('Use STAGE=JSON_PATH')
        inputs.append(existing_report(path,stage))
    output=args.output.resolve()
    if output.exists():parser.error('Use a fresh output path; historical reports are preserved')
    if output in [Path(value.partition('=')[2]).resolve() for value in args.input]:parser.error('Output cannot replace an input')
    result=report('verification_index','existing_stage_reports',[],status='indexed_without_reinterpretation',
                  limits=['Indexing does not execute a validator or establish end-to-end success.'])
    result['stages']=inputs
    save_report(output,result)
    print(output)


if __name__=='__main__':main()
