"""
다른 곳(챗봇형 Claude 등)에서 받은 op-amp 넷리스트를 우리 시스템과 같은 잣대로 채점한다 (시스템 비교 실험용).

    1. 넷리스트 정리: .subckt ~ .ends 만 꺼내 이름을 opamp 로, GF180 소자 줄(M... nfet_06v0 W= L=)을 우리 모양
       (XM... nfet_06v0 w=..u l=..u)으로. 단위가 없는 W/L 은 1 이상이면 µm, 아주 작으면 m 로 본다
    2. 동작점: 전압 팔로워로 묶어 출력이 VCM(2.5 V) 근처인지, 꺼진 소자·포화 영역 밖 소자가 있는지 (3단계와 같은 검사)
    3. 우리 측정: 비교할 실행의 판정 기준(spec.json)과 측정 부하로 재고 판정 (3~7단계와 같은 run_sim)
    4. 하네스 에이전트: 그 실행의 데이터시트 추출 결과로 데이터시트 전체 검증 (8단계와 같은 run_harness.py)
결과: <출력 폴더>/grade.json, grade.md (표). 우리 실행의 결과도 같은 표에 나란히 적는다.

사용법 (WSL 가상환경, edai 폴더에서):
    ~/.venvs/edai/bin/python grade_netlist.py runs/20261128_095408_lm358 챗봇답.cir --tag claude_opus
    --no-harness : 8단계 검증은 건너뜀 (1~2분 줄어듦)
    --answer 답.txt : 챗봇 답 전체 글. 글자 수로 출력 토큰을 대략 셈 (정확한 토큰은 API 기록을 쓸 것)
"""

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import auto_size          # noqa: E402
import run_sim            # noqa: E402

DESIGN_NAME = "grade_chatbot"     # run_sim 이 읽는 회로 파일 이름 (HERE/<이름>.cir, 채점 뒤 지움)
PORTS = ("INP", "INN", "OUT", "VDD", "VSS")
GF180 = {"nfet_06v0": "nmos", "pfet_06v0": "pmos"}
CHARS_PER_TOKEN = 3.0             # 한·영 섞인 답의 대략값 (참고용)


# ---------------------------------------------------------------- 1. 넷리스트 정리
def _size(value: str) -> str:
    """W/L 값 -> '10u' 모양. 단위 없으면 1e-3 미만은 m, 그 이상은 µm 로 본다."""
    v = value.strip().lower().replace("µ", "u").replace("μ", "u")
    m = re.fullmatch(r"([-+]?\d*\.?\d+(?:e[-+]?\d+)?)(u|n|m|p)?", v)
    if not m:
        return value
    number, unit = float(m.group(1)), m.group(2)
    if unit:
        return f"{number * {'u': 1, 'n': 1e-3, 'm': 1e3, 'p': 1e-6}[unit]:g}u"
    return f"{number * 1e6:g}u" if number < 1e-3 else f"{number:g}u"


def clean_netlist(text: str) -> tuple:
    """(우리 모양 .subckt 글, 정리 기록 목록, 구조 표). .subckt 가 없으면 ValueError."""
    lines, notes, inside, header = [], [], False, None
    for raw in text.splitlines():
        s = raw.strip()
        low = s.lower()
        if low.startswith(".subckt"):
            inside, header = True, s.split()
            continue
        if inside and low.startswith(".ends"):
            break
        if inside and s:
            lines.append(s)
    if header is None:
        raise ValueError("넷리스트에서 .subckt 를 찾지 못했어요")
    pins = header[2:]
    if [p.upper() for p in pins[:5]] != list(PORTS):
        notes.append(f"단자 이름이 {' '.join(pins)} 라서 순서대로 {' '.join(PORTS)} 로 봄")
    rename = {old: new for old, new in zip(pins[:5], PORTS)}
    out, rows = [f".subckt opamp {' '.join(PORTS)}"], []
    for s in lines:
        if s.startswith(("*", ";")):
            continue
        tokens = s.split()
        if s.startswith("+") and out:                  # 이어지는 줄
            out[-1] += " " + s[1:].strip()
            continue
        nets = lambda ts: [rename.get(t, t) for t in ts]
        if tokens[0][0].upper() in "MX" and len(tokens) >= 6 and tokens[5].lower() in GF180:
            name = tokens[0][1:] if tokens[0][0].upper() == "X" and tokens[0][1:2].upper() == "M" else tokens[0]
            name = re.sub(r"\W", "_", name).upper()
            params = []
            for t in tokens[6:]:
                if "=" in t:
                    k, v = t.split("=", 1)
                    k = k.lower()
                    params.append(f"{k}={_size(v)}" if k in ("w", "l") else f"{k}={v}")
            d, g, src, b = nets(tokens[1:5])
            out.append(f"X{name} {d} {g} {src} {b} {tokens[5].lower()} {' '.join(params)}")
            rows.append({"name": name, "kind": GF180[tokens[5].lower()], "pins": {"D": d, "G": g, "S": src, "B": b}})
        elif tokens[0][0].upper() in "RC" and len(tokens) >= 4:
            out.append(" ".join([tokens[0]] + nets(tokens[1:3]) + tokens[3:]))
        elif tokens[0][0].upper() == "M":
            raise ValueError(f"GF180 6 V 소자(nfet_06v0/pfet_06v0)가 아닌 트랜지스터: {s}")
        else:
            out.append(" ".join([tokens[0]] + nets(tokens[1:])))
            notes.append(f"그대로 둔 줄: {s[:60]}")
    out.append(".ends")
    table = {"ports": list(PORTS), "rows": rows}
    return "\n".join(out) + "\n", notes, table


# ---------------------------------------------------------------- 2·3. 동작점과 우리 측정
def operating_point(subckt: str, table: dict) -> dict:
    op = auto_size.run_op(subckt, table, ("INP", "INN"))
    if op.get("vout") is None:
        return {"ok": False, "reason": "동작점 계산 실패 (넷리스트 오류이거나 수렴 안 함)", "error": op.get("error")}
    report = auto_size.saturation_report(op, table)
    near = abs(op["vout"] - auto_size.VCM) <= auto_size.OUTPUT_TOLERANCE
    ok = near and not report["off"] and not report["triode"]
    reason = "" if ok else ("출력이 VCM 에서 벗어남" if not near else "꺼진 소자 또는 포화 영역 밖 소자")
    return {"ok": ok, "reason": reason, "vout": op["vout"], "off": report["off"], "triode": report["triode"]}


def measure(subckt: str, spec: dict) -> list:
    path = HERE / f"{DESIGN_NAME}.cir"
    path.write_text(subckt, encoding="utf-8")
    try:
        return run_sim.judge(run_sim.evaluate(DESIGN_NAME), spec)
    finally:
        path.unlink(missing_ok=True)
        for leftover in run_sim.OUT_DIR.glob(f"{DESIGN_NAME}*"):
            leftover.unlink(missing_ok=True)


# ---------------------------------------------------------------- 4. 하네스
def harness(run_dir: Path, subckt: str, table: dict, out_dir: Path) -> dict:
    """비교 실행의 추출 결과를 복사한 폴더에서 run_harness.py 를 돌린다 (실행 폴더는 건드리지 않음)."""
    work = out_dir / "harness_run"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for name in ("hkg.json", "datasheet.pdf", "input.json", "pages.json"):
        if (run_dir / name).exists():
            shutil.copy(run_dir / name, work / name)
    final = {"subckt": subckt, "table": " ; ".join(f"{r['name']} " + " ".join(f"{k}={v}" for k, v in r["pins"].items())
                                                  for r in table["rows"]),
             "rules": [], "passed": None, "judged": None, "output_scale": 1.0}
    (work / "final.json").write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    t0 = time.time()
    done = subprocess.run([sys.executable, str(HERE / "run_harness.py"), str(work)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    result_file = work / "harness" / "result.json"
    if done.returncode != 0 or not result_file.exists():
        return {"ok": False, "error": (done.stdout + done.stderr)[-600:], "seconds": round(time.time() - t0)}
    result = json.loads(result_file.read_text(encoding="utf-8"))
    return {"ok": True, "counts": result.get("counts"), "pass_rate": result.get("pass_rate_percent"),
            "seconds": round(time.time() - t0)}


# ---------------------------------------------------------------- 우리 실행 (같은 표에 나란히)
def our_run(run_dir: Path) -> dict:
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    final = json.loads((run_dir / "final.json").read_text(encoding="utf-8")) if (run_dir / "final.json").exists() else {}
    harness_result = run_dir / "harness" / "result.json"
    counts = json.loads(harness_result.read_text(encoding="utf-8")).get("counts") if harness_result.exists() else None
    llm = [s.get("llm") or {} for s in status.get("steps", [])]
    return {"state": status.get("state"), "seconds": status.get("total_seconds"),
            "llm_calls": sum(x.get("calls") or 0 for x in llm),
            "llm_cost_usd": round(sum(x.get("cost_usd") or 0 for x in llm), 4),
            "passed": final.get("passed"), "judged": final.get("judged"), "harness": counts}


def main() -> None:
    args = sys.argv[1:]
    run_dir, net_file = Path(args[0]).resolve(), Path(args[1]).resolve()
    tag = args[args.index("--tag") + 1] if "--tag" in args else net_file.stem
    out_dir = HERE / "runs_compare" / f"{run_dir.name}__{tag}"
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {"run": run_dir.name, "tag": tag, "netlist_file": str(net_file)}

    subckt, notes, table = clean_netlist(net_file.read_text(encoding="utf-8", errors="replace"))
    (out_dir / "netlist_clean.cir").write_text(subckt, encoding="utf-8")
    record.update(notes=notes, devices=len(table["rows"]))
    print(f"넷리스트 정리: 트랜지스터 {len(table['rows'])}개" + "".join(f"\n  - {n}" for n in notes), flush=True)

    spec = run_sim.load_spec(run_dir / "spec.json")
    record["op"] = operating_point(subckt, table)
    print(f"동작점: {'정상' if record['op']['ok'] else '문제 - ' + record['op']['reason']} "
          f"(출력 {record['op'].get('vout')}, 꺼진 소자 {record['op'].get('off')}, 포화 밖 {record['op'].get('triode')})", flush=True)
    try:
        rows = measure(subckt, spec)
        record["spec"] = [dict({k: r.get(k) for k in ("measure", "label", "unit", "value", "status")},
                               target=run_sim.target_text(r)) for r in rows]
        record["passed"] = sum(r["status"] == run_sim.STATUS_PASS for r in rows)
        record["judged"] = sum(r["status"] in (run_sim.STATUS_PASS, run_sim.STATUS_FAIL, run_sim.STATUS_UNMEASURED)
                               for r in rows)      # '참고'(보통값만 있는 항목)는 판정에 넣지 않음
        print(f"우리 측정: {record['passed']}/{record['judged']} 통과", flush=True)
    except Exception as error:
        record.update(spec=[], passed=0, judged=len(spec.get("specs", [])), measure_error=str(error)[:300])
        print(f"우리 측정 실패: {error}", flush=True)
    if "--no-harness" not in args:
        record["harness"] = harness(run_dir, subckt, table, out_dir)
        c = (record["harness"] or {}).get("counts") or {}
        print(f"하네스 에이전트: {c.get('passed')}/{c.get('judged')} 통과" if record["harness"].get("ok")
              else f"하네스 실패: {record['harness'].get('error', '')[-200:]}", flush=True)
    if "--answer" in args:
        answer = Path(args[args.index("--answer") + 1]).read_text(encoding="utf-8", errors="replace")
        record["answer_chars"] = len(answer)
        record["answer_tokens_approx"] = round(len(answer) / CHARS_PER_TOKEN)
    record["ours"] = our_run(run_dir)

    (out_dir / "grade.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    ours, h = record["ours"], (record.get("harness") or {}).get("counts") or {}
    oh = ours.get("harness") or {}
    lines = [f"# {run_dir.name} 비교: 우리 시스템 vs {tag}", "",
             "| 항목 | 우리 시스템 | " + tag + " |", "|---|---|---|",
             f"| 넷리스트 동작 (동작점) | 정상 | {'정상' if record['op']['ok'] else record['op']['reason']} |",
             f"| 우리 측정 통과 | {ours.get('passed')}/{ours.get('judged')} | {record.get('passed')}/{record.get('judged')} |",
             f"| 데이터시트 전체 검증 (하네스) | {oh.get('passed')}/{oh.get('judged')} | {h.get('passed')}/{h.get('judged')} |",
             f"| 걸린 시간 | {round((ours.get('seconds') or 0) / 60, 1)}분 (자동) | (직접 기록) |",
             f"| LLM 호출 / 비용 | {ours.get('llm_calls')}번 / ${ours.get('llm_cost_usd')} | (직접 기록) |"]
    if record.get("answer_tokens_approx"):
        lines.append(f"| 답 길이 (출력 토큰 대략) | - | 약 {record['answer_tokens_approx']} |")
    lines += ["", "## 항목별 (우리 측정)", "", "| 항목 | 값 | 목표 | 판정 |", "|---|---|---|---|"]
    for r in record["spec"]:
        value = "-" if r["value"] is None else f"{r['value']:.4g}"
        lines.append(f"| {r['label']} | {value} {r['unit']} | {r['target']} | "
                     f"{'통과' if r['status'] == run_sim.STATUS_PASS else '실패'} |")
    (out_dir / "grade.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"결과: {out_dir / 'grade.md'}", flush=True)


if __name__ == "__main__":
    main()
