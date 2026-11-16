# EDAI — 아날로그 IC 설계 자동화 및 피드백 시스템

아날로그 op amp의 요구사항을 정리하고 AI가 회로를 제안하면 LTspice가 동작/성능을 측정해 수정을 반복하는 시스템입니다. 이 브랜치는 다훈의 사양 추출·검사·설계 루프·하네스 작업을 공유합니다. 기준일:2026-11-16.

## 현재 상태

- 데이터시트 → 사양 검토 → HKG/PDG → 검사 계획 → 최초 설계 → 전체 검증/수정·이력·최선 회로 보존을 연결했습니다.
- 연속 하네스², 필요시 IEEE 본문/데이터시트 참고자료 선택, 성공 시 스케마틱 저장을 추가했습니다.
- 같은 LM358B 확대 계획에서 folded 기반 회로74/74·기동7/7, 새 비-folded 회로71/74·기동7/7을 확인했습니다. 별도29조건은 미검증입니다.
- 설계 모델 API, UI, 블록 조합은 아직 미통합입니다. AI 판단은 채팅/에이전트가 JSON으로 반환합니다. 추가 하네스의 성능/토큰 이점은 아직 입증하지 않았습니다.

## 먼저 볼 문서

| 내용 | 문서 |
|---|---|
| 이번 갱신과 기능/현재 한계 | [최신 변경](EDAI_OpAmp_Rebuild/docs/LATEST_UPDATE_20261116.md) |
| 설치·실행 | [설치 안내](EDAI_OpAmp_Rebuild/docs/SETUP_AND_RUN.md) |
| 전체 파일 역할 | [코드 지도](EDAI_OpAmp_Rebuild/docs/CODE_MAP.md) |
| 새 데이터시트로 시작 | [최초 설계 경로](EDAI_OpAmp_Rebuild/docs/COLD_START.md) |
| 연속 설계/지침 운영 | [운영 루프](EDAI_OpAmp_Rebuild/docs/CONTINUOUS_WORKFLOW.md) |
| 팀 파트 연결 | [팀 이관](EDAI_OpAmp_Rebuild/docs/TEAM_HANDOFF.md) |
| 대표 회로/조건/결과 | [2026-11-16 예시](EDAI_OpAmp_Rebuild/examples/lm358b_20261116/README.md) |

## 최소 환경

Windows·Python3.12·LTspice 환경에서 확인했습니다. 소스 문서와 API 키는 직접 준비합니다.

```powershell
cd EDAI_OpAmp_Rebuild
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

IEEE MCP를 사용할 경우 `requirements-ieee.txt`도 설치합니다. `.env.example`에 맞춰 로컬 키를 설정합니다. 기본 설정값은 새 데이터시트에 적절한지 먼저 확인하고, LTspice 경로와 선택적 MCP 의존 폴더도 실제 설치 환경에 맞게 지정합니다.

원래 `runs/` 파형/로그/문서 캐시·개인 환경은 포함하지 않았습니다. 예시는 읽기 전용 결과이며 다른 컴퓨터에서 과거 세션을 그대로 재개하는 백업은 아닙니다. 일반 MOS/25°C 범위의 구현 검증으로, 제조사 내부 회로 복제나 실제 IC 제작 검증은 아닙니다.
