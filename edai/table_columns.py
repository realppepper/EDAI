"""
추출한 스펙 줄의 최소/보통/최대를 데이터시트 표의 칸 위치로 다시 맞춘다.

왜 필요한가
    문서 읽기(nemotron-parse)는 표를 LaTeX tabular 로 넘겨서 MIN / TYP / MAX 칸 위치가 정확하다.
    그런데 그다음 LLM 이 값을 칸에 넣을 때, MIN 칸이 빈 줄의 값 두 개(예: 보통 80, 최대 170)를
    최소 80, 최대 170 으로 넣는 일이 잦았다 (LMV321 2.7 V 표의 ICC, IIB, IIO, 2026-11-25).
    목표값이 바뀌므로 (보통이 최소가 됨) 판정이 틀어진다.

하는 일
    1. 쪽 원문(pages.json)에서 MIN/TYP/MAX 머리줄이 있는 표를 찾아 줄마다 세 칸의 숫자를 읽는다
    2. 추출한 줄과 같은 쪽, 같은 기호(또는 이름), 같은 숫자 묶음인 표 줄을 찾는다
    3. 맞는 표 줄이 하나의 배치로만 읽히고 추출 배치와 다르면
    4. PDF 에 찍힌 숫자 위치(MIN/TYP/MAX 제목 아래 어느 칸인지)로 한 번 더 확인해서, 둘이 같을 때만 고치고 남긴다
    확실하지 않으면(맞는 줄이 없거나, 배치가 둘 이상이거나, PDF 위치가 다르면) 그대로 둔다.
"""

import re

FIELDS = ("min", "typ", "max")
NUMBER = re.compile(r"^[−–\-+]?\d+(?:\.\d+)?(?:\(\d\))?$")


def _clean(cell: str) -> str:
    """표 칸 글자에서 서식만 걷어 낸다."""
    cell = re.sub(r"\\(?:multirow|multicolumn)\{[^}]*\}\{[^}]*\}\{(.*)\}", r"\1", cell.strip())
    cell = re.sub(r"\\thead\{(.*)\}", r"\1", cell)
    cell = re.sub(r"<sup>.*?</sup>|<sub>|</sub>|\*\*|\\mbox\{\}", "", cell)
    return cell.strip()


def _cells(line: str) -> list:
    """한 줄을 칸으로 나눈다 (\\multicolumn{n} 은 n 칸)."""
    out = []
    for cell in re.split(r"(?<!\\)&", line):              # 빈 칸은 "& &" 로 붙어 있어 & 마다 나눈다
        m = re.match(r"\s*\\multicolumn\{(\d+)\}", cell)
        out += [_clean(cell)] * (int(m.group(1)) if m else 1)
    return out


def _number(cell: str):
    """칸이 숫자 하나면 그 값, 아니면 None ("250(1)" -> 250, "VCC − 100" -> None)."""
    cell = cell.replace(" ", "")
    if not NUMBER.match(cell):
        return None
    return float(re.sub(r"\(\d\)$", "", cell).replace("−", "-").replace("–", "-"))


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def table_rows(page_text: str) -> list:
    """쪽 원문의 MIN/TYP/MAX 표 줄: [{"label": 기호+이름 글자, "values": {"min": x, "typ": y, "max": z}}]."""
    rows = []
    for table in re.findall(r"\\begin\{tabular\}\{[^}]*\}\n(.*?)\\end\{tabular\}", page_text, re.S):
        lines = [l for l in table.split("\\\\\n") if l.strip()]
        cols, width, label = None, 0, ""
        for line in lines:
            cells = _cells(line)
            heads = [c.upper() for c in cells]
            if cols is None:
                if all(any(h.startswith(f.upper()) for h in heads) for f in FIELDS):
                    cols = {f: next(i for i, h in enumerate(heads) if h.startswith(f.upper())) for f in FIELDS}
                    width = len(cells)
                continue
            if len(cells) != width:
                continue                                    # 칸 수가 머리줄과 다르면 위치를 믿을 수 없다
            if cells[0] or cells[1]:
                label = cells[0] + " " + cells[1]           # 여러 줄에 걸친 항목은 위 줄 이름을 이어 쓴다
            values = {f: _number(cells[i]) for f, i in cols.items()}
            if any(v is not None for v in values.values()):
                rows.append({"label": _key(label), "values": values})
    return rows


LINE_TOL_PT = 3.0          # 같은 줄로 보는 세로 차이 [pt]


def _pdf_layouts(doc, page: int, numbers: list) -> set:
    """PDF 에 찍힌 위치로 본 칸 배치. numbers 가 모두 한 줄(세로 3 pt 안)에 있는 곳마다, 각 숫자가 바로 위
    MIN/TYP/MAX 제목 중 가로로 가장 가까운 칸에 있다고 보고 (min, typ, max) 를 만든다."""
    words = doc[page - 1].get_text("words")
    heads = []                                              # [(y, {min: x, typ: x, max: x})], 세로 3 pt 안은 한 줄
    for x0, y0, x1, y1, text, *_ in sorted(words, key=lambda w: w[1]):
        name = re.sub(r"\(\d\)$", "", text).upper()
        if name in ("MIN", "TYP", "MAX"):
            if not heads or y0 - heads[-1][0] > LINE_TOL_PT:
                heads.append((y0, {}))
            heads[-1][1][name.lower()] = (x0 + x1) / 2
    header_rows = [(y, cols) for y, cols in heads if len(cols) == 3]
    found = {}
    for x0, y0, x1, y1, text, *_ in words:
        value = _number(text)
        if value is not None:
            found.setdefault(value, []).append(((x0 + x1) / 2, y0))
    layouts = set()
    for _, y in found.get(numbers[0], []):
        spots = []
        for n in numbers:
            near = [p for p in found.get(n, []) if abs(p[1] - y) <= LINE_TOL_PT and p not in spots]
            if not near:
                break
            spots.append(near[0])
        if len(spots) != len(numbers):
            continue
        above = [cols for hy, cols in header_rows if hy < y]
        if not above:
            continue
        cols = above[-1]
        layout = dict.fromkeys(FIELDS)
        for n, (x, _) in zip(numbers, spots):
            layout[min(cols, key=lambda f: abs(cols[f] - x))] = n
        layouts.add(tuple(layout[f] for f in FIELDS))
    return layouts


def fix_columns(raw: dict, pages: dict, pdf=None) -> list:
    """raw["electrical_parameters"] 를 제자리에서 고치고, 고친 내용 목록을 돌려준다.
    pdf (PDF 경로) 를 주면 PDF 에 찍힌 위치로 한 번 더 확인해 둘이 같을 때만 고친다 (문서 읽기 표가 칸을
    한 칸 밀어 읽는 일이 있어서. LM358B AOL 고온 줄 35 V/mV 가 MIN 인데 표에는 TYP 칸, 2026-11-25).
    pdf 가 없으면 고치지 않는다."""
    if pdf is None:
        return []
    import pymupdf
    doc = pymupdf.open(str(pdf))
    by_page = {}
    fixes = []
    for i, row in enumerate(raw.get("electrical_parameters", [])):
        page = row.get("page")
        text = pages.get(str(page)) or pages.get(page)
        if not text:
            continue
        if page not in by_page:
            by_page[page] = table_rows(text)
        got = {f: row.get(f) for f in FIELDS}
        numbers = sorted(float(v) for v in got.values() if isinstance(v, (int, float)))
        if not numbers:
            continue
        names = [k for k in (_key(row.get("symbol")), _key(row.get("name"))) if k]
        layouts = set()
        for t in by_page[page]:
            if not any(n in t["label"] for n in names):
                continue
            if sorted(v for v in t["values"].values() if v is not None) == numbers:
                layouts.add(tuple(t["values"][f] for f in FIELDS))
        if len(layouts) != 1:
            continue                                        # 못 찾았거나 두 가지로 읽혀 확실하지 않음
        layout = layouts.pop()
        table = dict(zip(FIELDS, layout))
        if all((got[f] is None and table[f] is None) or (got[f] is not None and table[f] is not None
                                                          and float(got[f]) == table[f]) for f in FIELDS):
            continue
        if not isinstance(page, int) or not 1 <= page <= len(doc) or _pdf_layouts(doc, page, numbers) != {layout}:
            continue                                        # PDF 위치가 다르거나 확인할 수 없으면 그대로 둔다
        for f in FIELDS:
            row[f] = table[f]
        fixes.append({"row": i, "symbol": row.get("symbol"), "page": page, "conditions": row.get("test_conditions"),
                      "before": got, "after": table})
    doc.close()
    return fixes
