# 전체 코드 지도

파일 이름의 앞부분은 기능, 숫자는 그 기능 안의 대략적인 처리 순서입니다. 서로 다른 계열의 숫자를 전체 실행 순서로 해석하지 않습니다. `verify_04_dc_coverage`와 `verify_04_input_impedance`는 독립 기능으로 둘 다 보존했습니다.

## 핵심 모듈

| 파일 | 역할 |
|---|---|
| [opamp_pipeline/chart_01_collect.py](../opamp_pipeline/chart_01_collect.py) | 원문 그림·캡션 후보와 검토 입력 수집 |
| [opamp_pipeline/chart_02_verify.py](../opamp_pipeline/chart_02_verify.py) | 그림 메타데이터 검토 적용·사양 참고 연결 |
| [opamp_pipeline/design_01_cmos_candidate.py](../opamp_pipeline/design_01_cmos_candidate.py) | 동결 일반 MOS 모델과 최초 후보 구성 |
| [opamp_pipeline/design_02_check_bias.py](../opamp_pipeline/design_02_check_bias.py) | MOS 동작점·바이어스 해석 |
| [opamp_pipeline/design_03_cascoded_bias.py](../opamp_pipeline/design_03_cascoded_bias.py) | 캐스코드 기준 전류/바이어스 후보 |
| [opamp_pipeline/design_04_folded_input.py](../opamp_pipeline/design_04_folded_input.py) | folded 입력단 후보 구성 |
| [opamp_pipeline/design_05_overload_clamp.py](../opamp_pipeline/design_05_overload_clamp.py) | 과부하 회복 클램프 후보 구성 |
| [opamp_pipeline/diag_01_convergence.py](../opamp_pipeline/diag_01_convergence.py) | 수치 수렴 조건 대조 보조 도구 |
| [opamp_pipeline/diag_02_startup_seed.py](../opamp_pipeline/diag_02_startup_seed.py) | 실제 기동 파형에서 수치 초기 힌트 구성 |
| [opamp_pipeline/diag_03_solver_attempts.py](../opamp_pipeline/diag_03_solver_attempts.py) | 계산 실패 시 원래 계산 조건 재시도·저장 신호 선택 |
| [opamp_pipeline/harness_01_fixed.py](../opamp_pipeline/harness_01_fixed.py) | 고정 지침 로딩과 허용 DUT 경계 |
| [opamp_pipeline/harness_02_request.py](../opamp_pipeline/harness_02_request.py) | 전체 목표·피드백 요청 및 응답 계약 |
| [opamp_pipeline/harness_03_loop.py](../opamp_pipeline/harness_03_loop.py) | 최초/후보 저장·재검증·best·예산·중단/재개 |
| [opamp_pipeline/hkg_01_build.py](../opamp_pipeline/hkg_01_build.py) | 사양·조건·출처·검토 상태 HKG 구성 |
| [opamp_pipeline/hkg_02_validate.py](../opamp_pipeline/hkg_02_validate.py) | HKG와 입력 문서의 구조·보존 검사 |
| [opamp_pipeline/hkg_query.py](../opamp_pipeline/hkg_query.py) | HKG 사양과 연결 문맥 조회 |
| [opamp_pipeline/legacy_comparison/spec_01_extract_rows.py](../opamp_pipeline/legacy_comparison/spec_01_extract_rows.py) | 과거 독립 사양 추출 비교 코드 |
| [opamp_pipeline/legacy_comparison/spec_03_merge_evidence.py](../opamp_pipeline/legacy_comparison/spec_03_merge_evidence.py) | 과거 두 사양 결과 비교/병합 코드 |
| [opamp_pipeline/loop_01_policy.py](../opamp_pipeline/loop_01_policy.py) | 이전 설계 루프의 목표/예산 정책 |
| [opamp_pipeline/loop_02_handoff.py](../opamp_pipeline/loop_02_handoff.py) | 공통 JSON 저장·이전 요청/응답 도구 |
| [opamp_pipeline/loop_03_controller.py](../opamp_pipeline/loop_03_controller.py) | 이전 수동 설계 루프 상태 관리 |
| [opamp_pipeline/loop_04_extended_policy.py](../opamp_pipeline/loop_04_extended_policy.py) | 전체 사례 비교·회귀/우선 목표 평가 |
| [opamp_pipeline/pdf_01_inventory.py](../opamp_pipeline/pdf_01_inventory.py) | PDF 전체 페이지·텍스트·단어 좌표·책갈피 목록 |
| [opamp_pipeline/pdf_02_page_plan.py](../opamp_pipeline/pdf_02_page_plan.py) | 목표 제품 관련 후보 페이지와 분류 근거 |
| [opamp_pipeline/pdf_03_render_pages.py](../opamp_pipeline/pdf_03_render_pages.py) | 선택 페이지 이미지 생성과 공통 JSON 저장 |
| [opamp_pipeline/pdf_04_parse_layout.py](../opamp_pipeline/pdf_04_parse_layout.py) | Nemotron Parse 호출·응답 해독·서명 기반 재사용 |
| [opamp_pipeline/pdf_05_check_layout.py](../opamp_pipeline/pdf_05_check_layout.py) | 파싱 구조·내용 누락 후보 검사 |
| [opamp_pipeline/pdg_01_build.py](../opamp_pipeline/pdg_01_build.py) | 원문/AI 주석에서 핀·채널·동작 관계 구성 |
| [opamp_pipeline/pdg_02_validate.py](../opamp_pipeline/pdg_02_validate.py) | PDG 주석·원문 근거·관계 무결성 검사 |
| [opamp_pipeline/pdg_03_audit.py](../opamp_pipeline/pdg_03_audit.py) | 채널 경로·전원·출처 기능 감사 |
| [opamp_pipeline/pdg_04_schedule.py](../opamp_pipeline/pdg_04_schedule.py) | 명시적인 분석/시간 정책과 실행 일정 |
| [opamp_pipeline/pdg_05_visualize.py](../opamp_pipeline/pdg_05_visualize.py) | PDG 검토 HTML/SVG 생성 |
| [opamp_pipeline/pipeline_01_verification.py](../opamp_pipeline/pipeline_01_verification.py) | 기본→입력 임피던스→과부하 검증 통합·자격/이력 확인 |
| [opamp_pipeline/plan_01_select_targets.py](../opamp_pipeline/plan_01_select_targets.py) | 원문 행별 프로젝트 범위 선택 |
| [opamp_pipeline/plan_02_measurements.py](../opamp_pipeline/plan_02_measurements.py) | 단위·전압식·조건을 검사 사례로 변환 |
| [opamp_pipeline/plan_03_execution_policies.py](../opamp_pipeline/plan_03_execution_policies.py) | 사례별 분석/자극/판정 실행 정책 |
| [opamp_pipeline/plan_04_validate.py](../opamp_pipeline/plan_04_validate.py) | 선택·측정·실행 정책의 일치 검사 |
| [opamp_pipeline/ref_01_ieee_server.py](../opamp_pipeline/ref_01_ieee_server.py) | 선택적 IEEE 제목·초록 검색 MCP 서버 |
| [opamp_pipeline/ref_02_retrieve.py](../opamp_pipeline/ref_02_retrieve.py) | 설계 참고 문헌 메타데이터 검색 |
| [opamp_pipeline/ref_03_design_context.py](../opamp_pipeline/ref_03_design_context.py) | 사양·참고 자료의 설계 문맥 구성 |
| [opamp_pipeline/spec_01_build_rows.py](../opamp_pipeline/spec_01_build_rows.py) | 원문 셀로 공통 사양 행과 안정된 ID 생성 |
| [opamp_pipeline/spec_02_enrich_rows.py](../opamp_pipeline/spec_02_enrich_rows.py) | 같은 행에 AI 의미/조건 주석 적용 |
| [opamp_pipeline/spec_03_verify_sources.py](../opamp_pipeline/spec_03_verify_sources.py) | 통합된 행을 원문·조건·각주와 대조 |
| [opamp_pipeline/support/atomic_files.py](../opamp_pipeline/support/atomic_files.py) | 고유 임시 파일과 Windows 잠금 재시도로 원자적 게시 |
| [opamp_pipeline/support/condition_annotations.py](../opamp_pipeline/support/condition_annotations.py) | 상속 조건·역할·대체 관계 주석 검증 |
| [opamp_pipeline/support/content_audit.py](../opamp_pipeline/support/content_audit.py) | 원문/파싱 내용 대조 |
| [opamp_pipeline/support/execution_state.py](../opamp_pipeline/support/execution_state.py) | 단계 완료·입력 지문·최신 산출물 확인 |
| [opamp_pipeline/support/graph_conditions.py](../opamp_pipeline/support/graph_conditions.py) | 특성곡선 조건과 의미 해석 보조 |
| [opamp_pipeline/support/native_tables.py](../opamp_pipeline/support/native_tables.py) | 원본 PDF 좌표 기반 표/셀 읽기 |
| [opamp_pipeline/support/parse_identity.py](../opamp_pipeline/support/parse_identity.py) | 파싱 결과의 원문 연결/동일성 |
| [opamp_pipeline/support/semantic_review.py](../opamp_pipeline/support/semantic_review.py) | 원문 의미 검토 패킷·AI 검토 검증 |
| [opamp_pipeline/support/source_checks.py](../opamp_pipeline/support/source_checks.py) | 원문 단어/숫자/단위 대조와 지문 |
| [opamp_pipeline/support/stability_receipt.py](../opamp_pipeline/support/stability_receipt.py) | 안정성 측정 근거·자격 확인 |
| [opamp_pipeline/tb_01_reference_benches.py](../opamp_pipeline/tb_01_reference_benches.py) | 이론값이 알려진 기본 회로 벤치 |
| [opamp_pipeline/tb_02_ltspice.py](../opamp_pipeline/tb_02_ltspice.py) | 격리된 LTspice 배치 실행·로그/측정값 읽기 |
| [opamp_pipeline/tb_03_validate_reference.py](../opamp_pipeline/tb_03_validate_reference.py) | 기준값·누락·비유한 수치 판정 |
| [opamp_pipeline/tb_04_opamp_fixtures.py](../opamp_pipeline/tb_04_opamp_fixtures.py) | 분석용 이상 op amp와 기본 벤치 |
| [opamp_pipeline/tb_05_waveform_metrics.py](../opamp_pipeline/tb_05_waveform_metrics.py) | ASCII 파형·정착시간/오버슈트 해석 |
| [opamp_pipeline/tb_06_loop_gain.py](../opamp_pipeline/tb_06_loop_gain.py) | 이중 주입 루프 이득·교차점·위상여유 |
| [opamp_pipeline/verify_01_fixtures.py](../opamp_pipeline/verify_01_fixtures.py) | 원문 조건을 실제 op/dc/ac/tran/noise 벤치로 구성 |
| [opamp_pipeline/verify_02_metrics.py](../opamp_pipeline/verify_02_metrics.py) | 파형에서 수치 추출·동작/모델 성립 게이트 |
| [opamp_pipeline/verify_03_calibrate.py](../opamp_pipeline/verify_03_calibrate.py) | 기본 검사와 DC 두 경로의 정상/미달 기준 검증 |
| [opamp_pipeline/verify_04_dc_coverage.py](../opamp_pipeline/verify_04_dc_coverage.py) | 선언된 DC 격자 완전성·VCM 경로·제한된 수치 재시도 |
| [opamp_pipeline/verify_04_input_impedance.py](../opamp_pipeline/verify_04_input_impedance.py) | 차동/공통모드 입력 임피던스 및 R/C 해석 |
| [opamp_pipeline/verify_05_overload_recovery.py](../opamp_pipeline/verify_05_overload_recovery.py) | 포화/해제 프로토콜과 양방향 회복 측정 |

## 실행 진입점

| 파일 | 용도 |
|---|---|
| [run_bias_probe.py](../run_bias_probe.py) | 동작점 대조 보조 |
| [run_chart_references.py](../run_chart_references.py) | 특성곡선 검토·사양 연결(주 경로) |
| [run_convergence_diagnostic.py](../run_convergence_diagnostic.py) | 수치 수렴 점검 보조 |
| [run_design_context.py](../run_design_context.py) | 선택적 IEEE 참고 문맥 |
| [run_design_loop.py](../run_design_loop.py) | 이전 루프 보존 |
| [run_extended_design_loop.py](../run_extended_design_loop.py) | 이전 확장 루프 보존 |
| [run_extended_verification.py](../run_extended_verification.py) | 기본 확장 검사 단독 실행 |
| [run_fault_validation.py](../run_fault_validation.py) | 의도적 오류 검출 확인 |
| [run_first_opamp.py](../run_first_opamp.py) | 이전 최초 후보 실험 |
| [run_fixed_harness_loop.py](../run_fixed_harness_loop.py) | 설계자 전달·재검증·중단/재개(현재 주 경로) |
| [run_hkg.py](../run_hkg.py) | HKG 생성·검사(주 경로) |
| [run_input_impedance_extension.py](../run_input_impedance_extension.py) | 입력 임피던스 확장 단독 실행 |
| [run_load_diagnostic.py](../run_load_diagnostic.py) | 출력 부하 원인 점검 보조 |
| [run_measurement_plan.py](../run_measurement_plan.py) | 목표·검사 계획(주 경로) |
| [run_opamp_testbench_validation.py](../run_opamp_testbench_validation.py) | 이상 op amp 벤치 대조 |
| [run_overload_extension.py](../run_overload_extension.py) | 과부하 확장 단독 실행 |
| [run_pdf_layout.py](../run_pdf_layout.py) | 이미지 생성·Nemotron 파싱(주 경로) |
| [run_pdf_overview.py](../run_pdf_overview.py) | PDF 탐색·후보 페이지(주 경로) |
| [run_pdg.py](../run_pdg.py) | PDG 생성·감사·정책/화면(주 경로) |
| [run_seeded_diagnostic.py](../run_seeded_diagnostic.py) | 기동 힌트 적용 대조 보조 |
| [run_spec_pipeline.py](../run_spec_pipeline.py) | 행 생성→AI 주석→원문 검증(주 경로) |
| [run_stability_validation.py](../run_stability_validation.py) | 루프 이득/위상여유 측정법 대조 |
| [run_testbench_validation.py](../run_testbench_validation.py) | 기본 회로 이론값 대조 |
| [run_verification_pipeline.py](../run_verification_pipeline.py) | 세 검사 단계 통합(현재 주 경로) |

## 테스트와 보조 파일

`tests/`는 실행 없이 구조를 확인하는 검사, 원문이 필요한 선택 통합 검사, 오류 주입/복구 검사를 함께 담습니다. 다음 이름으로 찾으면 됩니다.

- `test_atomic_files.py`, `test_validation_recovery.py`, `test_pipeline_process_recovery.py`: 저장·동일 후보 재개·로그 보존.
- `test_dc_coverage.py`: 중간점 누락·중복 위장·분할 경계·수치 재시도.
- `test_extended_verification.py`, `test_input_impedance.py`, `test_overload_recovery.py`: 측정/판정.
- `test_fixed_harness.py`, `test_fixed_loop_control.py`, `test_fixed_loop_resume.py`: 고정 지침·루프.
- `test_pdf*`, `test_parse*`, `test_native_tables.py`, `test_sequential_specs.py`, `test_semantic_review.py`: 문서·사양.
- `test_hkg.py`, `test_pdg.py`, `test_pdg_upgrade.py`, `test_measurement_plan.py`: 그래프·계획.

`tools/migrate_reviewed_semantics.py`는 과거 검토 결과를 순차 주석으로 옮긴 일회성 도구입니다. `tools/verify_pdg_viewer.cjs`는 PDG 화면 검토용이며 Python 주 실행의 필수 의존성이 아닙니다.

`docs/BEFORE_SEQUENTIAL_REFACTOR.md`, `docs/PDG_UPGRADE_20261113.md`는 당시 개발 경위입니다. 현재 구현 범위는 README와 최신 문서를 우선합니다.
