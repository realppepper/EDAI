"""화면이 오류 없이 열리고 기록이 끝까지 그려지는지 가상의 사용자로 확인한다.

단계 넘기기와 차례로 나타나는 동작은 브라우저의 스크립트가 맡으므로 여기서는 확인하지 않는다
(내용은 처음에 모두 그려 두고 보이는 순서만 스크립트가 조절한다).

실행 (WSL, 프로젝트 폴더에서):
    ~/.venvs/edai/bin/pip install pytest pytest-asyncio     # 최초 1회
    ~/.venvs/edai/bin/python -m pytest tests -q
먼저 run_sim.py opamp_a opamp_b --select 와 llm_design.py 로 sim_out 에 기록이 있어야 한다.
"""
import pytest
from nicegui.testing import User

pytest_plugins = ["nicegui.testing.user_plugin"]

STEP_TITLES = ("데이터시트에서 설계 목표 추출", "후보 구조 비교와 선정", "소자 크기 결정과 반복 개선",
               "최종 설계의 항목별 검증")


@pytest.mark.asyncio
async def test_all_steps_are_drawn(user: User) -> None:
    await user.open("/")
    for text in STEP_TITLES + ("후보 1", "후보 2", "선정 근거", "1회차", "4회차", "대표 항목",
                               "계단 입력에 대한 출력 · RL 10 kΩ, CL 50 pF"):
        await user.should_see(text, retries=40)


@pytest.mark.asyncio
async def test_static_view_opens(user: User) -> None:
    await user.open("/?static=1")
    for text in STEP_TITLES:
        await user.should_see(text, retries=40)


@pytest.mark.asyncio
async def test_cascode_page_opens(user: User) -> None:
    await user.open("/cascode")
    await user.should_see("진행 단계")
