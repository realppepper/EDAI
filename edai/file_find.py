"""
파일 찾기 공통 함수: 파일 이름의 대소문자를 무시한다.

같은 코드가 Windows(대소문자 무시)와 WSL(대소문자 구분) 양쪽에서 돌고, 다른 프로그램(박준석 시스템, LLM)이
만드는 파일은 실행마다 이름의 대소문자가 다르다 (예: TLV271_FINAL_HERMES_HARNESS2.cir / TLV271_final_hermes_harness2.cir,
TLV271.PDF / OPA2376.pdf). Windows 에서는 찾는데 WSL 에서는 못 찾는 문제가 두 번 있었다 (2026-11-22).
다른 프로그램이 만든 파일을 이름으로 찾을 때는 Path.glob / == 대신 이 함수를 쓴다.

    find_files(folder, "*_design_summary.json")   -> 맞는 파일 목록 (이름순)
    find_file(folder, "*final_hermes_harness2.cir") -> 첫 번째 파일 또는 None
    name_key("TLV271.PDF") == name_key("tlv271.pdf")
"""

import fnmatch
from pathlib import Path


def name_key(name: str) -> str:
    """이름 비교용 열쇠 (소문자)."""
    return Path(str(name).replace("\\", "/")).name.lower()


def find_files(folder, pattern: str) -> list:
    """folder 안에서 pattern(*, ? 가능)에 맞는 파일. 대소문자 무시, 이름순."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    key = pattern.lower()
    return sorted((p for p in folder.iterdir() if p.is_file() and fnmatch.fnmatchcase(p.name.lower(), key)),
                  key=lambda p: p.name.lower())


def find_file(folder, pattern: str):
    """find_files 의 첫 번째 또는 None."""
    found = find_files(folder, pattern)
    return found[0] if found else None
