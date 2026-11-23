"""
박준석 하네스(이 저장소 루트의 ai_analog_designer)를 ngspice 로 돌리게 하는 연결 코드 (2026-11-23).

main 의 하네스는 시뮬레이터를 LTspice(Windows) 로만 부른다. 우리는 WSL 의 ngspice + GF180 PDK 를 쓰므로,
박준석 파일은 고치지 않고 하네스를 부르기 전에 실행 중에만 시뮬레이터 호출을 바꾼다 (install()).

    1. LTspiceRunner.run_netlist / __init__     -> sim_backend.run_spice (LTspice 문법 회로를 ngspice 로 옮겨 돌리고,
                                                   결과를 LTspice 형식 .log 로 써서 기존 파서가 그대로 읽게 함)
    2. deterministic_testbench 의 subprocess.run([LTSPICE_EXE, "-b", 파일]) -> 같은 run_spice
    3. 나머지 subprocess 호출은 그대로

sim_backend.py 는 지윤이 박준석 코드 복사본(edai/ngspice-sim 브랜치)에서 만든 변환기를 그대로 옮긴 것.
환경변수: AV_SIMULATOR (ngspice|ltspice, 기본 ngspice), AV_NGSPICE, AV_PDK_DIR (sim_backend.py 참고)
"""

import os
import subprocess

import sim_backend

_installed = False


class _SubprocessProxy:
    """subprocess 모듈 대신: LTspice 를 부르는 run 만 ngspice 로 보내고 나머지는 그대로."""

    def __init__(self, ltspice_exe: str):
        self._ltspice = ltspice_exe

    def run(self, args, *a, **kw):
        if isinstance(args, (list, tuple)) and len(args) >= 3 and args[0] == self._ltspice and args[1] == "-b":
            sim_backend.run_spice(str(args[2]), timeout=kw.get("timeout") or 60, ltspice_exe=self._ltspice)
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.run(args, *a, **kw)

    def __getattr__(self, name):
        return getattr(subprocess, name)


def install() -> bool:
    """하네스 모듈을 불러오기 전에 한 번 부른다. ngspice 로 바꿨으면 True (AV_SIMULATOR=ltspice 면 아무것도 안 함)."""
    global _installed
    if _installed or sim_backend.SIMULATOR != "ngspice":
        return _installed
    import glob

    from ai_analog_designer.neuro_symbolic_verifier import deterministic_testbench, ltspice_runner

    runner = ltspice_runner.LTspiceRunner

    def __init__(self, simulator_path=None):
        self.simulator_path = simulator_path or ltspice_runner.LTSPICE_EXE      # LTspice 가 없어도 됨

    def run_netlist(self, netlist_path, timeout=60):
        netlist_path = os.path.abspath(netlist_path)
        workdir = os.path.dirname(netlist_path)
        base = os.path.splitext(os.path.basename(netlist_path))[0]
        log_file = os.path.join(workdir, f"{base}.log")
        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except OSError:
                pass
        try:
            sim_backend.run_spice(netlist_path, timeout=timeout, ltspice_exe=self.simulator_path)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"ngspice timed out after {timeout} seconds on {netlist_path}") from exc
        if not os.path.exists(log_file):
            found = glob.glob(os.path.join(workdir, f"{base}*.log"))
            if not found:
                raise RuntimeError(f"Log file not generated for {netlist_path} (ngspice)")
            log_file = found[0]
        return self.parse_log(log_file)

    runner.__init__ = __init__
    runner.run_netlist = run_netlist
    deterministic_testbench.subprocess = _SubprocessProxy(ltspice_runner.LTSPICE_EXE)
    _installed = True
    return True
