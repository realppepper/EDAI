"""
Unified Ngspice Runner Adapter.
Complements `ltspice_runner.py` so AnalogVerifier can execute both Windows LTspice
and ngspice (including GF180 PDK testbenches from jiyun's pipeline) behind a clean interface.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


class NgspiceRunner:
    """Headless ngspice batch simulator wrapper."""

    def __init__(self, ngspice_exe: str | None = None, pdk_dir: str | None = None):
        local_ngspice = Path.home() / "ngspice" / "bin" / "ngspice"
        self.ngspice_exe = (
            ngspice_exe
            or os.environ.get("EDAI_NGSPICE")
            or shutil.which("ngspice")
            or shutil.which("ngspice_con")
            or (str(local_ngspice) if local_ngspice.is_file() else "")
        )
        self.pdk_dir = pdk_dir or os.environ.get(
            "EDAI_PDK_DIR",
            str(Path.home() / "pdk" / "gf180mcu_fd_pr" / "models" / "ngspice"),
        )

    def is_available(self) -> bool:
        return bool(self.ngspice_exe and Path(self.ngspice_exe).is_file())

    def has_gf180_pdk(self) -> bool:
        return Path(self.pdk_dir, "design.ngspice").is_file()

    def run_netlist(self, cir_path: str, timeout_s: float = 60.0) -> dict[str, Any]:
        if not self.is_available():
            return {"success": False, "error": "ngspice executable not found.", "log": ""}
        cir = Path(cir_path).resolve()
        raw_path = cir.with_suffix(".raw")
        log_path = cir.with_suffix(".log")
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [self.ngspice_exe, "-b", "-r", str(raw_path), "-o", str(log_path), str(cir)],
                cwd=cir.parent,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"ngspice timed out after {timeout_s}s", "log": ""}
        log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else proc.stdout + proc.stderr
        return {
            "success": proc.returncode == 0 and raw_path.is_file(),
            "returncode": proc.returncode,
            "elapsed_s": round(time.monotonic() - t0, 3),
            "raw_path": str(raw_path) if raw_path.is_file() else None,
            "log_path": str(log_path) if log_path.is_file() else None,
            "log": log_text,
        }
