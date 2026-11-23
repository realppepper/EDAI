import glob
import os
import re
import subprocess

_CANDIDATES = [
    os.environ.get("LTSPICE_PATH", ""),
    r"D:\Program Files\LTspice\LTspice.exe",
    r"C:\Program Files\LTspice\LTspice.exe",
    r"C:\Program Files\ADI\LTspice\LTspice.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\ADI\LTspice\LTspice.exe"),
    r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe",
]
LTSPICE_EXE = next((p for p in _CANDIDATES if p and os.path.exists(p)), _CANDIDATES[1])

class LTspiceRunner:
    def __init__(self, simulator_path=None):
        self.simulator_path = simulator_path or LTSPICE_EXE
        from .sim_backend import SIMULATOR
        if SIMULATOR != "ngspice" and not os.path.exists(self.simulator_path):
            raise FileNotFoundError(f"LTspice not found at {self.simulator_path}")

    def run_netlist(self, netlist_path, timeout=60):
        """Runs LTspice in batch mode and parses measurement results."""
        netlist_path = os.path.abspath(netlist_path)
        workdir = os.path.dirname(netlist_path)
        base_name = os.path.splitext(os.path.basename(netlist_path))[0]
        log_file = os.path.join(workdir, f"{base_name}.log")

        if os.path.exists(log_file):
            try:
                os.remove(log_file)
            except Exception:
                pass

        # Run without -ascii to prevent crash on .noise analyses
        # EDAI: AV_SIMULATOR=ngspice(기본) 면 ngspice + GF180 PDK 로 돌리고 LTspice 형식 .log 를 쓴다 (sim_backend.py)
        from .sim_backend import run_spice
        try:
            run_spice(netlist_path, timeout=timeout, ltspice_exe=self.simulator_path)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Simulator timed out after {timeout} seconds on {netlist_path}") from exc
        proc = subprocess.CompletedProcess([], 0, "", "")

        if not os.path.exists(log_file):
            candidates = glob.glob(os.path.join(workdir, f"{base_name}*.log"))
            if candidates:
                log_file = candidates[0]
            else:
                raise RuntimeError(f"Log file not generated for {netlist_path}. LTspice output: {proc.stdout} {proc.stderr}")

        return self.parse_log(log_file)

    def parse_log(self, log_path):
        """Extracts all measurement (.meas) values from the LTspice log file."""
        results = {}
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line in lines:
            line_str = line.strip()

            # Ignore non-meas lines
            line_lower = line_str.lower()
            if any(line_lower.startswith(k) for k in ["direct newton", "solver", "maximum", "total elapsed", "tnom", "temp", "method", "asciirawfile", "gmin", "vernier", "starting", "source step"]):
                continue

            # Case 1: Complex AC measurement:
            # e.g.: "avol_at_1hz: V(out)=(105.53dB,-11.31°) at 1"
            m_ac = re.match(r"^([a-zA-Z0-9_]+)\s*:\s*.*=\s*\(\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)dB\s*,\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)[°\w]*\)", line_str, re.IGNORECASE)
            if m_ac:
                var_name = m_ac.group(1).lower()
                results[f"{var_name}_db"] = float(m_ac.group(2))
                results[f"{var_name}_phase"] = float(m_ac.group(3))
                continue

            # Case 2: Standard real number measurement:
            # e.g.: "vos: v(in_p)-v(in_n)=0.000108344 at 0.001" or "vos=-0.000108344"
            m_real = re.match(r"^([a-zA-Z0-9_]+)(?:\s*:[^=]+)?\s*=\s*([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)(?:\s+at.*)?$", line_str, re.IGNORECASE)
            if m_real:
                var_name = m_real.group(1).lower()
                val = float(m_real.group(2))
                results[var_name] = val
                continue

            # Case 3: Failed / unobserved measurement:
            m_fail = re.match(r"^Measurement:\s*([a-zA-Z0-9_]+)", line_str, re.IGNORECASE)
            if m_fail:
                var_name = m_fail.group(1).lower()
                if var_name not in results:
                    results[var_name] = None

        return results
