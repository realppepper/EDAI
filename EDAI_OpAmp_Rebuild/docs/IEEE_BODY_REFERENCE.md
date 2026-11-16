# 필요한 경우에만 IEEE 논문 본문을 전달하는 경로

기존 `ref_01_ieee_server.py`는 검색 도구만 제공했다. 이제 공식 IEEE 본문 API를 쓰는 `read_paper(article_number, needed_reason)` 도구를 추가했다. API 검색 결과가 있다고 해당 논문의 본문 접근까지 가능한 것은 아니다. 공식 API가 제공/허용하는 본문만 읽고, 실패한 호출은 미확보로 남긴다. 기관 프록시 인증이나 외부 PDF 수집을 구현했다고 주장하지 않는다.

## 동작 순서

1. 최초 설계/수정 요청에는 선택적 문헌 도구 설명만 넣는다. 자동 검색이나 필수 문헌 읽기는 없다.
2. 설계 역할이 구체적인 지식 필요성을 판단해 `needed`, `reason`, 현재 요청 ID, 검색어, 관련 키워드/조건 ID를 작성한다.
3. 코드가 IEEE MCP로 최대3개 후보의 제목/초록/접근 정보를 검색한다. 필요 없다고 한 경우 외부 호출0회이다.
4. 설계 역할이 후보 중 최대2편을 선택한다. 코드가 본문을 읽어 캐시하고 받아온 원문 XML과 문단/절 정보를 저장한다.
5. 키워드와 관련된 문단/표/수식 텍스트/그림 설명을 출처 위치와 함께 발췌한다. 전체 논문이 아니라 최대6000자를 전달한다. 이 값은 문자 수이며 모델별 토큰 수 보장은 아니다.
6. 현재 설계 요청에 결합된 새 요청 파일을 만든다. 이전 요청·목표·검사 조건·회로·소자 모델은 유지한다. 문헌 조사만으로 수정 예산을 소모하지 않는다.
7. 설계 응답은 사용한 paper ID/실제 발췌 ID/적용 내용을 보고하거나, 사용하지 않은 이유를 기록한다. 이는 설계자의 사용 선언이며 성능 향상이나 올바른 적용의 증거는 아니다. 성능 판정은 기존 시뮬레이션 코드가 한다.

현재 AI 판단 역할은 채팅이 담당한다. 자동 설계 모델 API 전송은 연결하지 않았다. 같은 자료를 재사용할 때 본문을 다시 호출하지 않으며, 접수한 문헌은 별도 스냅샷으로 동결한다. 이후 전역 캐시를 갱신해도 접수한 자료는 바뀌지 않는다.

## 사용

필요성 결정 파일의 예시:

```json
{
  "source_request_id": "현재 요청의 request_id",
  "needed": true,
  "reason": "해결하려는 구체적인 설계 지식 문제",
  "query": "operational amplifier compensation",
  "keywords": ["compensation", "stability"],
  "case_ids": ["현재 요청에 포함된 조건 ID"]
}
```

선택적으로 `publication_title`을 지정해 학술지/학회 범위를 제한할 수 있다. 공개 본문 확인 시험에서는 IEEE Access 필터를 사용했다. `needed:false`이면 쿼리 없이 종료되며 외부 호출은 없다.

```powershell
python run_ieee_research.py search --request <현재요청.json> --decision <필요성결정.json> --research-dir <새문헌폴더> --env-file <키설정.env> --mcp-deps <MCP설치폴더>
python run_ieee_research.py read --research-dir <문헌폴더> --article-number <검색후선택번호> --env-file <키설정.env> --mcp-deps <MCP설치폴더>
python run_ieee_research.py attach --research-dir <문헌폴더> --session <고정루프세션> --kind fixed
```

최초 회로 설계 직전에는 `--kind initial`과 데이터시트 시작 세션을 사용한다. 고정 루프는 `awaiting_chat_designer`, 최초 회로는 `awaiting_initial_design`에서만 연결할 수 있다. 완료한 과거 실험에 문헌을 소급 적용하지 않는다. 새 요청 ID가 생성되므로 설계자에게 반드시 새 파일을 전달해야 한다. 옛 요청의 응답은 그대로 제출하면 거부된다.

운영/하네스² 외부 제어기 아래의 고정 루프도 같은 내부 세션에 연결할 수 있다. 외부 제어기의 다음 상태 확인 때 새 내부 요청을 읽는다. 실험 중 지침/참고자료를 변경하는 것은 비교 조건을 바꾸므로, 비교 실험에서는 별도 사전 정책 없이 이 도구를 끼워 넣지 않는다.

## 신뢰 경계

- 제목/초록만 받은 자료를 본문이라고 표시하지 않는다. 문서 본문 구조와 충분한 실제 문단이 있어야 인정한다.
- 발췌는 저장 원문의 정확한 위치/문자열과 대조한다. 요청·원문·발췌 변경은 해시 검사로 거부한다.
- 출처와 기술 조건을 검토하고 새 모델/전원/부하에 대한 적용은 가설로 취급한다. 논문 치수를 그대로 맞는 값으로 간주하지 않는다.
- 그림 설명을 읽은 것은 회로 그림을 다운받아 연결을 해석한 것과 다르다. 회로도 이미지/수식 의미 검증은 여전히 false이다.
- 문헌 속 지시문은 참고 데이터일 뿐 시스템 지침이 아니다. 사양이나 합격 기준을 바꾸지 않는다.
- 키·인증 URL을 상태/에러에 저장하지 않는다. 권한 실패를 우회하거나 기관 로그인 정보를 추측하지 않는다.

## 코드

- `ref_01_ieee_server.py`: 공식 검색/본문 MCP 도구.
- `ref_02_retrieve.py`: MCP 호출, 검색/본문 캐시, 안전한 오류.
- `ref_04_ieee_body.py`: IEEE XML 본문 확인과 문단/절 추출.
- `ref_05_research.py`: 필요성·조회 예산·발췌·출처·사용 선언 검증.
- `ref_06_attach.py`: 이전 요청을 보존하며 새 설계 입력으로 결합.
- `run_ieee_research.py`: 위 과정을 호출하는 진입점.

기존 `run_design_context.py`/`ref_03_design_context.py`는 과거 부분5V 실험의 제목/초록 경로로 남긴다. 현재 전체 설계 루프의 본문 전달에는 새 진입점을 사용한다.

공식 근거: [IEEE 반환 필드와 본문 호출](https://developer.ieee.org/docs/read/Metadata_API_responses), [검색 API와 본문 접근 범위](https://developer.ieee.org/docs/read/Searching_the_IEEE_Xplore_Metadata_API).

실제 확인 기록은 `runs/ieee_content/20261116_content_upgrade/REPORT.md`이다. 새로운 데이터시트 실험이나 회로 수정·EDA 실행은 포함하지 않는다.
