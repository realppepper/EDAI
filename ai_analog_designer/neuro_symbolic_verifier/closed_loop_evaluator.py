import os
from typing import Any

from .ltspice_runner import LTspiceRunner
from .sympy_oracle_engine import SymPyOracleEngine


class ClosedLoopEvaluator:
    """
    Coordinates simulation execution via LTspice, parses measurements,
    evaluates SymPy formal oracles, and generates diagnostic feedback
    for iterative LLM circuit refinement.
    """

    def __init__(self, simulator_path: str | None = None):
        self.runner = LTspiceRunner(simulator_path=simulator_path) if simulator_path else LTspiceRunner()
        self.oracle_engine = SymPyOracleEngine()

    def evaluate_circuit(
        self,
        output_dir: str,
        netlist_filename: str,
        testbenches: list[dict[str, Any]],
        specifications: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Executes all testbenches, collects measurements, and evaluates all specifications.
        """
        os.makedirs(output_dir, exist_ok=True)

        # 1. Filter specifications testable via SPICE (exclude thermal/storage packaging limits)
        sim_specs = [
            s for s in specifications
            if not any(k in s.get("symbol", "").lower() for k in ["tstg", "θja", "theta", "hbm", "mm", "cdm", "esd"])
        ]
        if not sim_specs:
            sim_specs = specifications

        # Build SymPy oracles
        oracles = [self.oracle_engine.build_oracle(s) for s in sim_specs]

        # 2. Execute each testbench
        all_measurements = {}
        execution_logs = []
        simulation_errors = []

        for tb in testbenches:
            tb_name = tb["name"]
            tb_path = os.path.join(output_dir, f"tb_{tb_name}.cir")
            with open(tb_path, "w", encoding="utf-8") as f:
                f.write(tb["content"])

            log_path = os.path.join(output_dir, f"tb_{tb_name}.log")
            try:
                meas = self.runner.run_netlist(tb_path)
                all_measurements.update(meas)

                # Check for warnings or errors in log file
                log_errors = self._extract_log_errors(log_path)
                if log_errors:
                    simulation_errors.extend(log_errors)

                execution_logs.append({
                    "testbench": tb_name,
                    "status": "SUCCESS" if not log_errors else "WARNING",
                    "measurements": meas,
                    "log_messages": log_errors
                })
            except Exception as e:
                log_errors = self._extract_log_errors(log_path)
                err_msg = str(e)
                if log_errors:
                    err_msg += f" | Log errors: {' '.join(log_errors)}"
                simulation_errors.append(err_msg)
                execution_logs.append({
                    "testbench": tb_name,
                    "status": "ERROR",
                    "error": err_msg
                })

        # 3. Match measurements to oracles and evaluate
        spec_evaluations = []
        passed_count = 0
        failed_count = 0
        unmeasured_count = 0

        for oracle in oracles:
            sym_name = oracle["symbol"]
            clean_sym = oracle["clean_symbol"]

            measured_val = self._find_measurement(clean_sym, sym_name, all_measurements)
            eval_res = self.oracle_engine.evaluate(oracle, measured_val)
            spec_evaluations.append(eval_res)

            if eval_res["passed"]:
                passed_count += 1
            elif eval_res["measured"] is None:
                unmeasured_count += 1
            else:
                failed_count += 1

        total_specs = len(sim_specs)
        pass_rate = (passed_count / total_specs * 100.0) if total_specs > 0 else 0.0

        # 4. Generate structured LLM diagnostic feedback
        diagnostic_text = self._generate_diagnostic_feedback(spec_evaluations, simulation_errors)

        return {
            "total_specs": total_specs,
            "passed_specs": passed_count,
            "failed_specs": failed_count,
            "unmeasured_specs": unmeasured_count,
            "pass_rate_percent": pass_rate,
            "all_passed": (passed_count == total_specs and total_specs > 0),
            "spec_evaluations": spec_evaluations,
            "all_measurements": all_measurements,
            "execution_logs": execution_logs,
            "simulation_errors": simulation_errors,
            "diagnostic_feedback": diagnostic_text
        }

    def _extract_log_errors(self, log_path: str) -> list[str]:
        """Extracts syntax, fatal, or convergence errors from LTspice log with code context."""
        if not os.path.exists(log_path):
            return []
        errors = []
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines):
            line_str = line.strip()
            line_lower = line_str.lower()
            if any(term in line_lower for term in [
                "syntax error", "fatal error", "error:", "cannot be instantiated", 
                "unknown parameter", "already defined", "expected node", "expected model", 
                "expected a sequence", "monotonically increasing", "model name expected",
                "node or model name", "unknown subcircuit", "trouble with", "singular matrix",
                "matrix is singular", "time step too small", "circuit contains these syntax errors",
                "is not defined", "not defined", "number of nodes",
                "are paralleled", "over-defined", "circuit matrix"
            ]):
                errors.append(line_str)
                for offset in [1, 2]:
                    if idx + offset < len(lines):
                        nxt = lines[idx + offset].strip()
                        if nxt and not nxt.startswith("---") and not nxt.startswith("Circuit:"):
                            errors.append(f"  --> {nxt}")
        return errors[:12]

    def _find_measurement(self, clean_sym: str, raw_sym: str, measurements: dict[str, float]) -> float | None:
        """Finds measurement corresponding to specification symbol."""
        c_lower = clean_sym.lower()
        r_lower = raw_sym.lower()
        no_us = c_lower.replace("_", "")

        # 1. Exact match
        if c_lower in measurements:
            return measurements[c_lower]
        if r_lower in measurements:
            return measurements[r_lower]
        if no_us in measurements:
            return measurements[no_us]

        # 2. Look for target key prefix or suffix in measurements
        for k, v in measurements.items():
            k_lower = k.lower()
            if k_lower.startswith(f"{c_lower}_") or k_lower.endswith(f"_{c_lower}"):
                return v
            if k_lower.startswith(f"{no_us}_") or k_lower.endswith(f"_{no_us}"):
                return v

        # 3. Fuzzy substring containment
        for k, v in measurements.items():
            k_lower = k.lower()
            if c_lower in k_lower or no_us in k_lower:
                return v

        return None

    def _generate_diagnostic_feedback(self, evaluations: list[dict[str, Any]], sim_errors: list[str]) -> str:
        """Constructs physical guidance feedback for AI circuit re-synthesis."""
        lines = []

        if sim_errors:
            lines.append("## LTSPICE COMPILATION / SIMULATION ERRORS (MUST FIX):")
            for err in sim_errors[:8]:
                lines.append(f"- {err}")
            lines.append("")

        failures = [e for e in evaluations if not e["passed"]]
        if not failures and not sim_errors:
            return "All specifications passed successfully! No repair needed."

        lines.append("## FAILED SPECIFICATIONS AUDIT:")
        for idx, f in enumerate(failures, 1):
            sym = f["symbol"]
            meas = f.get("measured")
            min_t = f.get("min_target")
            max_t = f.get("max_target")
            unit = f.get("unit", "")
            diag = f.get("diagnostic", "")

            lines.append(f"{idx}. Parameter '{sym}': {diag}")
            if meas is not None:
                lines.append(f"   Target: Min={min_t}, Max={max_t} {unit} | Actual Measured={meas:.4g}")
            else:
                lines.append(f"   Target: Min={min_t}, Max={max_t} {unit} | Measurement was NOT observed in simulation.")

        lines.append("\nRECOMMENDED ACTIONS FOR CIRCUIT ARCHITECT:")
        lines.append("- Correct any SPICE syntax, unique component naming, or subcircuit pin order issues.")
        lines.append("- Review component sizing (W/L of input transistors, bias branch currents, compensation capacitance).")
        lines.append("- Check internal node voltage drops and operating regions (ensure saturation for active MOSFETs).")
        lines.append("- Adjust drive buffer strength to satisfy dynamic/transient timing bounds.")

        return "\n".join(lines)
