# LM358B 25°C 읽기용 예시

| 파일 | 내용 |
|---|---|
| `specifications.json` | 42행의 값·조건·원문 쪽과 행 ID 요약 |
| `pdg.json` | 핀/채널/동작 관계의 구조 사본 |
| `candidate_18p.inc` | 엄격한 검증에서58조건을 통과한 일반 MOS 단일 채널 회로 |
| `candidate_80p.inc` | 비교에 사용한 보상값80pF의 미달 출발 회로 |
| `verification_cases.json` | 원래80조건의 목표·시험 조건·최종 판정 요약 |
| `comparison_single_round.json` | 한 번씩 수정한 기본/지침 비교 성적과 예외 |
| `stability_summary.json` | 저장·재개 보완 확인 요약 |

개인 경로와 실행 메타데이터를 제거/축약한 **읽기용 사본**입니다. 원본 전체 실행 대장과 해시를 그대로 재현한 체크포인트가 아니므로 `runs/`나 `--run-dir`에 복사해서 resume하지 않습니다. 실제 실행은 원문과 검토 파일부터 생성한 유효한 run 폴더를 요구합니다.

18pF 회로와80pF 회로는 평가용 일반 모델이며 TI 칩의 내부 회로나 제조용 설계가 아닙니다. 데이터시트에서 채택한 프로젝트 목표와 제품 전체 보증을 구분하세요. 자세한 판정 범위와 정정은 [결과·한계](../../docs/RESULTS_AND_LIMITATIONS.md)에 있습니다.
