# 조원 하네스 지침 검토 — 고정 v1

기본 C1–C4 전체와 C5–C8의 실제 연결, 기존 architect 프롬프트, 경험 파일7개를 확인했습니다. 내용은 실행하지 않고 원문 데이터로 읽었습니다. 기대 효과를 판단해 선별한 것이며 성능 향상은 아직 비교 실험으로 입증하지 않았습니다.

| 원문 항목 | 판단 | 이유/적용 |
|---|---|---|
| C1 production-quality/all specifications | 수정 | 일반 MOS·1채널·25C 및 실제 검증 범위로 제한. 원문 전체 제조 보장은 근거가 없음. |
| C1 PDG physical startup | 수정 | 논리 의존성과 프로젝트의 시간 정책을 구분. 미확인 지연을 사실로 주지 않음. |
| C2 subckt/pin order | 채택·구체화 | FIRSTAMP P N VP VM OUT 고정. LM358 패키지8핀을 그대로 옮기지 않음. |
| C2 ground isolation | 채택·코드강제 | DUT 내부0 대신VM/VP. 양전원·PSRR 시험과 일관되게 유지. |
| C2 freely define MOS/BJT/diode models | 교체 | GNM/GPM 계수 고정 및M/R/C만 허용. 새 모델 정의·이상적 소스로 목표 우회 금지. |
| C2 physical-only mandate | 범위수정 | 설계 DUT에 적용. 외부 측정 회로의 B/E/V/I와 기준 회로는 허용. |
| C2 structural/device syntax | 선별채택 | 중복 이름·단자수·숫자 형식·분석 명령 금지. 현재 인터페이스에 없는 BJT/JFET/인덕터/중첩X는 제외. |
| C2 dual-channel instruction | 보류 | 현재는1채널. 독립 복사2개로 채널 결합을 검증했다고 주장하지 않음. |
| C3 mandatory100Meg leakage path | 조건부수정 | 저항은 고이득 노드를 부하로 만들 수 있음. DC경로·이득·기동 교환관계를 확인. |
| C3 ClassAB diodes/Vbe multiplier | 조건부수정 | 항상 이 구조를 강제하지 않고 출력단 방식에 맞게 교차왜곡·대기전류·단락전류를 확인. |
| C3 bandgap PTAT recipe | 범위축소 | 밴드갭 레시피는 제외, 자기 바이어스 회로의 기동 확인 원칙만 유지. |
| C3 fixed Cc5-30p/Rz1-5k | 수치제외 | 단일 숫자 범위는 근거 부족. 실제 바이어스·부하의 검증 결과로 결정. 현재680Ohm Rz도 검증된 사용례. |
| C4 all .meas aligned to PDG | 교체 | 현재 op/dc/ac/tran 파형·Tian·노이즈 등 각 측정 정의를 사용. 모든 측정이 PDG의 특정 시각 .meas는 아님. |
| C4 startup20us/50us examples | 제외 | 예시를 제조사 요구로 사용하지 않음. 검사 코드의 현재 시작·관측 창을 전달. |
| C4 XML output | 교체 | 요청 ID에 결합된 엄격한 JSON+완전한 넷리스트. 부분 XML 자동 보정은 사용하지 않음. |
| LM358 learned Rz=1/gm, sizing ranges | 조건부·수치제외 | 특정 토폴로지 근사와 경험 숫자. 현재 회로에서 별도 확인 없이 강제하지 않음. |
| LM358 learned curly-brace claim | 수정 | LTspice 일반 문법을 단정하지 않음. 현재 검증기는 숫자 값만 허용한다는 인터페이스 제약으로 표현. |
| LM358 blueprint Cc/Rz syntax | 제외 | 같은 이름 Cc 재사용과 세미콜론 뒤 명령 예시가 모호함. 고정 W/L/전류·Iref·모델 범위 검증 근거도 부족. |
| Other six experience families | 제외 | 비교기·555·밴드갭·오디오전력 회로 경험을 opamp 고정 지침에 자동 주입하지 않음. 과거 통과율을 재사용하지 않음. |
| Legacy architect omit noise/temp | 제외 | 현재 미검증 잡음을 생략·통과로 바꾸는 근거가 될 수 없음.25C 범위와 모델 한계를 명시. |
| C5 default | 선별작성 | 빈 기본값과 특정 LM358 예제는 그대로 가져오지 않고 현재 후보와 조건부 설계 지식만 사용. |
| C6-C8 declarations | 명시적구현/보류 | C6은 계산의 근사성 안내, C7은 비활성, C8은 자체 검증기로 강제. 조원 코드에서 이미 모두 작동한다고 가정하지 않음. |
| Harness library bootstrapping | 비활성 | 이번 루프에서 파일 해시로 지침을 고정. 경험 자동학습과 Harness²는 이후 별도 단계. |

설계자 역할은 현재 채팅입니다. 설계용 API 호출과 모델 자동 전환은 사용하지 않습니다. 원문 지침은 source_inventory.json에 보존하고 실행 지침은 fixed_v1.json의 선별 문장만 사용합니다. Harness² 지침 변경은 비활성입니다.