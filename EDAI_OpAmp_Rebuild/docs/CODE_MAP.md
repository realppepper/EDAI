# 전체 코드 지도 — 2026-11-16

숫자는 각 기능 안의 처리 순서입니다. 런타임 Python은 원본과 동일하며, 두 테스트의 로컬 자료 탐색만 공유 fixture fallback을 유지합니다. [최신 변경](LATEST_UPDATE_20261116.md)을 먼저 확인하세요.

| 파일 | 역할 |
|---|---|
| [__init__.py](../opamp_pipeline/__init__.py) | Independent, staged op-amp datasheet pipeline. No legacy runtime imports. |
| [chart_01_collect.py](../opamp_pipeline/chart_01_collect.py) | Collect typical-characteristic chart evidence without adopting target values. |
| [chart_02_verify.py](../opamp_pipeline/chart_02_verify.py) | Attach visual review with explicit temperature scope and source safeguards. |
| [design_01_cmos_candidate.py](../opamp_pipeline/design_01_cmos_candidate.py) | First transistor op-amp candidate. Educational LEVEL1 models, no PDK claims. |
| [design_02_check_bias.py](../opamp_pipeline/design_02_check_bias.py) | Nominal LEVEL1 headroom diagnostic, not a temperature-corrected device OP oracle. |
| [design_03_cascoded_bias.py](../opamp_pipeline/design_03_cascoded_bias.py) | Supply-insensitive MOS beta-multiplier proposal; frozen models unchanged. |
| [design_04_folded_input.py](../opamp_pipeline/design_04_folded_input.py) | PMOS input folded-cascode proposal for the remaining input-range/gain goals. |
| [design_05_overload_clamp.py](../opamp_pipeline/design_05_overload_clamp.py) | Optional all-MOS anti-windup candidate; frozen model coefficients retained. |
| [diag_01_convergence.py](../opamp_pipeline/diag_01_convergence.py) | Diagnostic-only numerical changes; never loosen acceptance or force a DC state. |
| [diag_02_startup_seed.py](../opamp_pipeline/diag_02_startup_seed.py) | Physical-ramp-derived initial guesses; no .ic, UIC, tolerance relaxation or added DUT elements. |
| [diag_03_solver_attempts.py](../opamp_pipeline/diag_03_solver_attempts.py) | Retry a numerical failure without changing the circuit, tolerances or acceptance. |
| [diag_04_vcm_points.py](../opamp_pipeline/diag_04_vcm_points.py) | Read-only circuit diagnosis: individual DC points, not sweep qualification. |
| [harness_01_fixed.py](../opamp_pipeline/harness_01_fixed.py) | Reviewed fixed instructions and enforced DUT boundaries; no provider or Harness² calls. |
| [harness_02_request.py](../opamp_pipeline/harness_02_request.py) | Full-scope request/response contract for current-chat or a future API transport. |
| [harness_03_loop.py](../opamp_pipeline/harness_03_loop.py) | Fixed-harness current-chat handoff loop. API transport and Harness² are disabled. |
| [harness_04_feedback.py](../opamp_pipeline/harness_04_feedback.py) | Describe existing verification evidence without changing verdicts or targets. |
| [harness_05_history.py](../opamp_pipeline/harness_05_history.py) | Observed adjacent-candidate history; never infer physical causes or edit rules. |
| [harness_06_evolution.py](../opamp_pipeline/harness_06_evolution.py) | Outer instruction-edit controller; each probe uses the unchanged fixed inner loop. |
| [harness_07_workflow.py](../opamp_pipeline/harness_07_workflow.py) | Bounded operational Harness2 rounds around the existing fixed design loop. |
| [hkg_01_build.py](../opamp_pipeline/hkg_01_build.py) | Lossless, typed property graph from reviewed spec candidates; no inference. |
| [hkg_02_validate.py](../opamp_pipeline/hkg_02_validate.py) | Graph integrity and source round-trip verification, not new circuit judgement. |
| [hkg_query.py](../opamp_pipeline/hkg_query.py) | Return a spec with its linked context without flattening its conditions. |
| [loop_01_policy.py](../opamp_pipeline/loop_01_policy.py) | Fixed partial-scope goals; challenge overrides never change datasheet sources. |
| [loop_02_handoff.py](../opamp_pipeline/loop_02_handoff.py) | Manual chat designer contract; a future API can produce the same response. |
| [loop_03_controller.py](../opamp_pipeline/loop_03_controller.py) | Persisted partial-scope loop: evaluate, stop, hand off, preserve best, resume. |
| [loop_04_extended_policy.py](../opamp_pipeline/loop_04_extended_policy.py) | Compare the full source-case ledger without erasing unknowns or regressions. |
| [pdf_01_inventory.py](../opamp_pipeline/pdf_01_inventory.py) | Step 1: inspect EVERY PDF page locally; no rendering or AI calls. |
| [pdf_02_page_plan.py](../opamp_pipeline/pdf_02_page_plan.py) | Step 2: make an auditable candidate-page map, without extracting spec values. |
| [pdf_03_render_pages.py](../opamp_pipeline/pdf_03_render_pages.py) | Step 3: render reviewed page categories, retaining PDF/image provenance. |
| [pdf_04_parse_layout.py](../opamp_pipeline/pdf_04_parse_layout.py) | Step 4: parse page images with Nemotron 3.5 Parse; no spec interpretation. |
| [pdf_05_check_layout.py](../opamp_pipeline/pdf_05_check_layout.py) | Step 5: structural checks, not certification of extracted spec values. |
| [pdg_01_build.py](../opamp_pipeline/pdg_01_build.py) | Build a source-reviewed port dependency graph, never a fabricated schedule. |
| [pdg_02_validate.py](../opamp_pipeline/pdg_02_validate.py) | Check PDG structure, graph provenance and no inferred activation timetable. |
| [pdg_03_audit.py](../opamp_pipeline/pdg_03_audit.py) | Channel completeness and provenance audit, inspired by legacy PDG checks. |
| [pdg_04_schedule.py](../opamp_pipeline/pdg_04_schedule.py) | Generate analysis-operation sequences or explicit-policy transient timing. |
| [pdg_05_visualize.py](../opamp_pipeline/pdg_05_visualize.py) | Standalone local PDG inspector with provenance, audit and policy views. |
| [pipeline_01_verification.py](../opamp_pipeline/pipeline_01_verification.py) | One entry for core, input impedance and overload; imported chains are hash-bound. |
| [plan_01_select_targets.py](../opamp_pipeline/plan_01_select_targets.py) | Select project targets without changing source data or temperature claims. |
| [plan_02_measurements.py](../opamp_pipeline/plan_02_measurements.py) | Op-amp measurement recipes inspired by the legacy spec planner. |
| [plan_03_execution_policies.py](../opamp_pipeline/plan_03_execution_policies.py) | Attach explicit engineering execution policies to measurement cases. |
| [plan_04_validate.py](../opamp_pipeline/plan_04_validate.py) | Validate source retention, goal provenance, fixtures and policy link coverage. |
| [ref_01_ieee_server.py](../opamp_pipeline/ref_01_ieee_server.py) | Read-only IEEE search and explicitly requested official full-text MCP. |
| [ref_02_retrieve.py](../opamp_pipeline/ref_02_retrieve.py) | MCP search with explicit trigger, content-addressed cache, safe failures. |
| [ref_03_design_context.py](../opamp_pipeline/ref_03_design_context.py) | Construct factual design input; abstracts are reference material, never rules. |
| [ref_04_ieee_body.py](../opamp_pipeline/ref_04_ieee_body.py) | Official IEEE full-text endpoint only; abstract/login pages never count as body. |
| [ref_05_research.py](../opamp_pipeline/ref_05_research.py) | Need-gated search, selected body reads, bounded source-exact design excerpts. |
| [ref_06_attach.py](../opamp_pipeline/ref_06_attach.py) | Attach selected literature to an awaiting request, retaining frozen prior requests. |
| [ref_07_datasheet.py](../opamp_pipeline/ref_07_datasheet.py) | Need-gated source-exact datasheet references, separate from accepted targets. |
| [schematic_01_export.py](../opamp_pipeline/schematic_01_export.py) | Deterministic LTspice DUT drawings for the current physical M/R/C adapter. |
| [spec_01_build_rows.py](../opamp_pipeline/spec_01_build_rows.py) | Create one canonical row set from original-PDF evidence, before AI enrichment. |
| [spec_02_enrich_rows.py](../opamp_pipeline/spec_02_enrich_rows.py) | Apply semantic-only AI annotations to the SAME immutable-source row set. |
| [spec_03_verify_sources.py](../opamp_pipeline/spec_03_verify_sources.py) | Final verification on the integrated document; row IDs persist end to end. |
| [startup_01_initial_design.py](../opamp_pipeline/startup_01_initial_design.py) | Source-reviewed project admission and an initial design request with no seed DUT. |
| [startup_02_datasheet.py](../opamp_pipeline/startup_02_datasheet.py) | Fresh PDF stages -> explicit source/policy handoffs -> new DUT -> operational loop. |
| [tb_01_reference_benches.py](../opamp_pipeline/tb_01_reference_benches.py) | Analytical calibration fixtures, not an op-amp design or datasheet pass test. |
| [tb_02_ltspice.py](../opamp_pipeline/tb_02_ltspice.py) | Run isolated batch jobs and read explicit .meas scalars. Never reuse old logs. |
| [tb_03_validate_reference.py](../opamp_pipeline/tb_03_validate_reference.py) | Compare measurements against analytical values; absent/nonfinite never pass. |
| [tb_04_opamp_fixtures.py](../opamp_pipeline/tb_04_opamp_fixtures.py) | Explicit five-terminal op-amp fixtures. Calibration defaults are NOT DUT specs. |
| [tb_05_waveform_metrics.py](../opamp_pipeline/tb_05_waveform_metrics.py) | Read LTspice ASCII real raw data and measure finite-window settling safely. |
| [tb_06_loop_gain.py](../opamp_pipeline/tb_06_loop_gain.py) | Tian dual-injection, following LTspice Educational/LoopGain2.asc. |
| [verify_01_fixtures.py](../opamp_pipeline/verify_01_fixtures.py) | Source-bound extended fixtures. Numeric grids/waveforms are explicit project settings. |
| [verify_02_metrics.py](../opamp_pipeline/verify_02_metrics.py) | Interpret extended simulations with validity gates and explicit model limitations. |
| [verify_03_calibrate.py](../opamp_pipeline/verify_03_calibrate.py) | Known-answer checks for new source-bound fixture methods before DUT verdicts. |
| [verify_04_dc_coverage.py](../opamp_pipeline/verify_04_dc_coverage.py) | Require every declared sample of an adapter's numeric one-source DC sweep. |
| [verify_04_input_impedance.py](../opamp_pipeline/verify_04_input_impedance.py) | Input two-port admittance and a declared symmetric parallel-R/C interpretation. |
| [verify_05_overload_recovery.py](../opamp_pipeline/verify_05_overload_recovery.py) | Explicit project overload protocol, saturation evidence and finite-window recovery. |
| [verify_06_batch.py](../opamp_pipeline/verify_06_batch.py) | Select a diagnostic batch while retaining the original full-plan inventory. |
| [verify_07_startup_gate.py](../opamp_pipeline/verify_07_startup_gate.py) | Project operating gate, separate from the datasheet's case count. |
| [verify_08_distortion.py](../opamp_pipeline/verify_08_distortion.py) | Deterministic distortion component only. Never label this THD+N compliance. |
| [run_bias_probe.py](../run_bias_probe.py) | Fast priority screen; full extended revalidation is still required afterward. |
| [run_chart_references.py](../run_chart_references.py) | Collect/review typical graphs and attach separate references to spec JSON. |
| [run_convergence_diagnostic.py](../run_convergence_diagnostic.py) | Compare unchanged DUTs under identical diagnostic numerical policies. |
| [run_datasheet_design.py](../run_datasheet_design.py) | Cold document handoffs and first-DUT generation; no historical netlist input. |
| [run_datasheet_references.py](../run_datasheet_references.py) | Select existing datasheet references only after a concrete design need. |
| [run_design_context.py](../run_design_context.py) | Search IEEE via MCP and prepare source-linked input for the design LLM. |
| [run_design_loop.py](../run_design_loop.py) | Manual-chat designer bridge. No polling and no paid LLM API invocation. |
| [run_extended_design_loop.py](../run_extended_design_loop.py) | Register chat-authored revisions and execute the full80-case validation loop. |
| [run_extended_verification.py](../run_extended_verification.py) | Three requested verification stages; all source rows remain in coverage ledger. |
| [run_fault_validation.py](../run_fault_validation.py) | Real LTspice negative controls. Faults live in isolated copies, never best DUT. |
| [run_first_opamp.py](../run_first_opamp.py) | First all-transistor LEVEL1 op-amp experiment, separately from calibration. |
| [run_fixed_harness_loop.py](../run_fixed_harness_loop.py) | Current chat is the designer; the deterministic host executes the full verification pipeline. |
| [run_harness2_loop.py](../run_harness2_loop.py) | Instruction proposal -> fixed control/probe loops -> whole-policy decision. |
| [run_hkg.py](../run_hkg.py) | Build HKG from current, completed source artifacts; no LLM/API call. |
| [run_ieee_research.py](../run_ieee_research.py) | Explicit need -> IEEE search -> selected body read -> bound design handoff. |
| [run_input_impedance_extension.py](../run_input_impedance_extension.py) | Qualified impedance measurement extension; existing55 passes and original80-case ledger stay intact. |
| [run_load_diagnostic.py](../run_load_diagnostic.py) | Separate follower input range from output-sink loading; never change source-case verdicts. |
| [run_measurement_plan.py](../run_measurement_plan.py) | Build 25 C measurement definitions and per-test execution policies only. |
| [run_model_capability_audit.py](../run_model_capability_audit.py) | Inventory unresolved cases and qualify deterministic THD without changing models. |
| [run_opamp_testbench_validation.py](../run_opamp_testbench_validation.py) | Validate op-amp fixture methods using a fully disclosed analytical calibration DUT. |
| [run_opamp_workflow.py](../run_opamp_workflow.py) | Continuous operational circuit/instruction rounds; no effect-comparison branch. |
| [run_overload_extension.py](../run_overload_extension.py) | Qualify overload timing then append both saturation directions to the unchanged80-case ledger. |
| [run_pdf_layout.py](../run_pdf_layout.py) | Run steps 3–4 on a saved page plan. Never calls a general-purpose LLM. |
| [run_pdf_overview.py](../run_pdf_overview.py) | Run the first two local-only steps, saving each stage for debugging. |
| [run_pdg.py](../run_pdg.py) | Build source-grounded PDG using current-chat annotations; no API invocation. |
| [run_seeded_diagnostic.py](../run_seeded_diagnostic.py) | Derive nodeset hints from a physical supply ramp, then release all hints for DC solving. |
| [run_spec_pipeline.py](../run_spec_pipeline.py) | Code rows -> semantic enrichment -> integrated-document verification. |
| [run_stability_validation.py](../run_stability_validation.py) | Analytic PM references, phase-wrap/impedance stress, and existing CMOS crosscheck. |
| [run_testbench_validation.py](../run_testbench_validation.py) | Calibrate LTspice measurement plumbing; no API or op-amp design. |
| [run_vcm_point_diagnostic.py](../run_vcm_point_diagnostic.py) | Inspect missing points of three saved candidates without rewriting their results. |
| [run_verification_pipeline.py](../run_verification_pipeline.py) | Unified qualification pipeline. No designer API calls. |
