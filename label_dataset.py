"""
구조 표에 auto_size.py 로 크기를 정하고, 테스트벤치로 성능을 재서 학습 데이터(성능 -> 구조)를 만든다.

사용법 (WSL, 프로젝트 폴더에서. 구조 하나에 20~30초):
    ~/.venvs/edai/bin/python label_dataset.py blocks          # 블록 조립 구조 32개로 도구 검증
    ~/.venvs/edai/bin/python label_dataset.py analoggenie 20  # AnalogGenie 구조 20개 (범주별로 고르게)
    ~/.venvs/edai/bin/python label_dataset.py analoggenie all
    python label_dataset.py rejudge data/labels_analoggenie_all.json   # 시뮬레이션 없이 "동작" 판정만 다시
    ~/.venvs/edai/bin/python label_dataset.py remeasure data/labels_blocks.json  # 동작하는 줄만 측정을 다시 (크기는 그대로)

결과: data/labels_<이름>.json
"동작"의 기준 (세 가지 모두. 데이터시트와 상관없이 OP-Amp 라면 같은 기준):
    1. 전압 팔로워로 묶었을 때 출력이 VCM 근처에 있다
    2. 모든 트랜지스터가 켜져 있고 포화 영역에 있다
    3. 부하 없이 잰 개방루프 이득이 VALID_MIN_GAIN_DB 이상이다
성능 값(대역폭, 위상여유, 2 kΩ 부하 이득, 전류 등)은 거르지 않고 그대로 기록한다.
이 값들은 데이터시트 조건(TLV271: 부하 2 kΩ, 10 kΩ 등)으로 잰 것이다.
구조 하나를 VARIANTS 의 (전류, 출력단 배율) 마다 따로 만들어 여러 줄의 데이터를 얻는다.
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

import auto_size
import netlist_table as nt
import run_sim
import topology

DATA_DIR = run_sim.HERE / "data"
DESIGN_NAME = "opamp_auto"            # run_sim 이 OP-Amp 로 알아보도록 opamp 로 시작한다
# 나눠 돌리기: EDAI_WORKER="i/n" 이면 remeasure 가 할 일의 i 번째 몫만 하고, 임시 회로 이름도 따로 쓴다
WORKER = os.environ.get("EDAI_WORKER")
if WORKER:
    DESIGN_NAME = f"opamp_w{WORKER.split('/')[0]}_"
VALID_MIN_GAIN_DB = 20.0          # 이 이상이면 "확실히 증폭한다"로 본다 (성능 기준이 아니라 동작 기준)
# 학습 데이터에 남기는 측정값 (run_sim.measure_opamp 의 이름)
KEPT_MEASURES = ("avd", "gain_dc", "ugbw", "pm", "gm", "idd", "sr", "ts", "cmrr", "psrr",
                 "voh_1ma", "voh_5ma", "vol_1ma", "vol_5ma", "io_source", "io_sink")


def measure(subckt: str) -> dict:
    """크기를 정한 회로를 테스트벤치 5종으로 잰다."""
    path = run_sim.HERE / f"{DESIGN_NAME}.cir"
    path.write_text("* label_dataset.py 가 만든 임시 회로\n" + subckt, encoding="utf-8")
    try:
        result = run_sim.evaluate(DESIGN_NAME)
        measured = result.get("measured", result)
        kept = {key: measured.get(key) for key in KEPT_MEASURES}
        kept["gain_unloaded"] = unloaded_gain()
    finally:
        path.unlink(missing_ok=True)
        for leftover in run_sim.OUT_DIR.glob(f"{DESIGN_NAME}*"):
            leftover.unlink()
    return kept


def unloaded_gain() -> float:
    """부하 없이 잰 저주파 개방루프 이득 [dB]. 회로 구조 자체가 증폭하는지 볼 때 쓴다."""
    raw = run_sim.run(run_sim.build_netlist(DESIGN_NAME, "ac", "noload", vdd=run_sim.OPAMP_VDD,
                                            rl=run_sim.OPAMP_NO_LOAD, cl=run_sim.OPAMP_AC_CL))
    return float(20 * np.log10(abs(np.array(raw.get_trace("v(out)").get_wave())[0])))


# (전류원 하나의 전류 [A], 출력단 전류 배율)
VARIANTS = ((20e-6, 1.0), (20e-6, 5.0))


def label(table: dict, passives: dict = None, unit_current: float = auto_size.UNIT_CURRENT,
          output_scale: float = 1.0) -> dict:
    started = time.time()
    sized = auto_size.auto_size(table, passives, unit_current, output_scale)
    record = {"unit_current": unit_current, "output_scale": output_scale, "op_ok": sized.get("vout") is not None and abs(sized["vout"] - auto_size.VCM) <= auto_size.OUTPUT_TOLERANCE,
              "saturated_all": sized["ok"], "off": sized.get("off"), "triode": sized.get("triode"),
              "startup": sized.get("startup"),
              "reason": sized.get("reason"), "iterations": sized.get("iterations"), "polarity": sized.get("polarity"),
              "transistors": len(auto_size.mos_rows(table))}
    record["measured"] = None
    if record["op_ok"]:
        try:
            record["measured"] = measure(sized["subckt"])
        except Exception as error:  # 수렴 실패 등
            record["measure_error"] = f"측정 실패: {str(error)[:200]}"
        record["sizes"] = sized["sizes"]
        record["subckt"] = sized["subckt"]
    judge(record)
    record["seconds"] = round(time.time() - started, 1)
    return record


def judge(record: dict) -> dict:
    """"동작" 여부와 이유를 정한다. 기준은 맨 위 설명의 세 가지. record 를 고쳐서 돌려준다."""
    measured = record.get("measured") or {}
    gain = measured.get("gain_unloaded")
    if not record["op_ok"]:
        reason = record.get("reason") or "출력이 VCM 에서 벗어남"
    elif record.get("off"):
        reason = f"꺼진 소자 {', '.join(record['off'])}"
    elif record.get("triode"):
        reason = f"포화 영역 밖 소자 {', '.join(record['triode'])}"
    elif record.get("measure_error"):
        reason = record["measure_error"]
    elif gain is None or gain < VALID_MIN_GAIN_DB:
        reason = f"무부하 이득 부족 ({gain if gain is None else round(gain, 1)} dB)"
    else:
        reason = ""
    record["valid"], record["reason"] = not reason, reason
    return record


def rejudge(path: Path) -> None:
    """이미 만든 결과 파일을 지금 기준으로 다시 판정한다 (시뮬레이션 없음)."""
    records = json.loads(path.read_text(encoding="utf-8"))
    before = sum(r["valid"] for r in records)
    for r in records:
        if (r.get("reason") or "").startswith("측정 실패"):  # 예전 형식: 측정 실패를 reason 에 적었다
            r["measure_error"] = r["reason"]
        startup = auto_size.startup_devices(nt.parse_table_text(r["table"]))
        r["off"] = [n for n in r.get("off") or [] if n not in startup]
        r["triode"] = [n for n in r.get("triode") or [] if n not in startup]
        r["startup"] = sorted(startup)
        judge(r)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    working = {r["name"] for r in records if r["valid"]}
    print(f"{path.name}: 동작 {before} -> {sum(r['valid'] for r in records)} / {len(records)} 줄, "
          f"구조 기준 {len(working)} / {len({r['name'] for r in records})}")


def block_items():
    library = topology.load_library()
    for selection, result in topology.all_structures():
        if result["errors"]:
            continue
        table = nt.to_table(nt.parse_ngspice(topology.netlist_text(selection, result["instances"], library)))
        passives = {row["name"]: row["params"] for row in table["rows"] if row["kind"] in ("res", "cap")}
        yield topology.structure_text(selection, library), table, passives


def analoggenie_items(count):
    data = json.loads((DATA_DIR / "opamp_tables.json").read_text(encoding="utf-8"))
    circuits = data["circuits"]
    if count != "all":
        step = max(1, len(circuits) // int(count))
        circuits = circuits[::step][:int(count)]
    for circuit in circuits:
        yield f"AnalogGenie {circuit['id']}", nt.parse_table_text(circuit["table"]), None


def record_key(r: dict) -> str:
    return f"{r['name']}|{r['unit_current']}|{r['output_scale']}"


def merge_shards(path: Path, records: list) -> None:
    """나눠 돌린 결과(<이름>.w#.json)를 본 파일에 합치고 지운다."""
    shards = sorted(path.parent.glob(f"{path.stem}.w*.json"))
    if not shards:
        return
    by_key = {record_key(r): r for r in records}
    for shard in shards:
        for key, updated in json.loads(shard.read_text(encoding="utf-8")).items():
            by_key[key].update(updated)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    for shard in shards:
        shard.unlink()
    print(f"{path.name}: 나눠 돌린 결과 {len(shards)}개를 합침", flush=True)


def remeasure(path: Path) -> None:
    """동작하는 줄을 저장된 회로(subckt)로 다시 측정해 KEPT_MEASURES 를 모두 채운다 (크기 정하기는 다시 하지 않음).
    이미 다 채운 줄은 건너뛰므로 중간에 멈춰도 이어서 돌릴 수 있다.
    EDAI_WORKER="i/n" 이면 i 번째 몫만 하고 결과를 <이름>.w<i>.json 에 따로 적는다.
    모두 끝난 뒤 EDAI_WORKER 없이 한 번 더 실행하면 합친다."""
    records = json.loads(path.read_text(encoding="utf-8"))
    if not WORKER:
        merge_shards(path, records)
    todo = [r for r in records if r["valid"] and r.get("subckt")
            and not all(key in (r["measured"] or {}) for key in KEPT_MEASURES)]
    shard_path, shard = None, {}
    if WORKER:
        index, total = (int(x) for x in WORKER.split("/"))
        todo = todo[index::total]
        shard_path = path.parent / f"{path.stem}.w{index}.json"
        shard = json.loads(shard_path.read_text(encoding="utf-8")) if shard_path.exists() else {}
        todo = [r for r in todo if record_key(r) not in shard]
    print(f"{path.name}: 다시 측정할 줄 {len(todo)}", flush=True)
    for count, r in enumerate(todo, 1):
        started = time.time()
        try:
            r["measured"] = measure(r["subckt"])
        except Exception as error:  # 수렴 실패 등. 예전 값은 그대로 두고 표시만 한다
            r["measure_error"] = f"측정 실패: {str(error)[:200]}"
        judge(r)
        print(f"  {count}/{len(todo)} {r['name']} (출력 x{r['output_scale']:g}) "
              f"{'동작' if r['valid'] else r['reason']}  ({time.time() - started:.1f} s)", flush=True)
        if shard_path:
            shard[record_key(r)] = {k: r.get(k) for k in ("measured", "measure_error", "valid", "reason") if k in r}
            shard_path.write_text(json.dumps(shard, ensure_ascii=False), encoding="utf-8")
        else:
            path.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "remeasure":
        for name in sys.argv[2:]:
            remeasure(Path(name))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "rejudge":
        for name in sys.argv[2:]:
            rejudge(Path(name))
        return
    if len(sys.argv) < 2 or sys.argv[1] not in ("blocks", "analoggenie"):
        print(__doc__)
        return
    mode = sys.argv[1]
    items = block_items() if mode == "blocks" else analoggenie_items(sys.argv[2] if len(sys.argv) > 2 else "20")
    out = DATA_DIR / f"labels_{mode}{'' if mode == 'blocks' else '_' + (sys.argv[2] if len(sys.argv) > 2 else '20')}.json"
    # 결과 파일이 있으면 이어서 돌린다 (중간에 멈췄을 때 처음부터 다시 하지 않도록)
    records = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    done = {(r["name"], r["unit_current"], r["output_scale"]) for r in records}
    if done:
        print(f"이미 있는 {len(done)} 줄은 건너뛴다 ({out.name})", flush=True)
    for name, table, passives in items:
        for unit_current, output_scale in VARIANTS:
            if (name, unit_current, output_scale) in done:
                continue
            record = {"name": name, "table": nt.table_text(table), **label(table, passives, unit_current, output_scale)}
            records.append(record)
            m = record["measured"] or {}
            shown = lambda v: "-" if v is None else round(v, 1)  # noqa: E731
            print(f"  {'동작' if record['valid'] else '실패'}  {name} (출력 x{output_scale:g})  무부하 이득 "
                  f"{shown(m.get('gain_unloaded'))} dB, 2k 부하 {shown(m.get('gain_dc'))} dB"
                  f"  {record['reason'] or ''}  ({record['seconds']} s)", flush=True)
            out.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    valid = sum(r["valid"] for r in records)
    structures = {r["name"] for r in records}
    working = {r["name"] for r in records if r["valid"]}
    print(f"동작 {valid} / {len(records)} 줄, 구조 기준 {len(working)} / {len(structures)}  -> {out.relative_to(run_sim.HERE)}")


if __name__ == "__main__":
    main()
