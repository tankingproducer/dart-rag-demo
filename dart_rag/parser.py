"""DART 공시 원문 XML → 섹션 트리(Section) / 표(Table) 구조화.

DART XML 골격:
<DOCUMENT><BODY>
  <SECTION-1><TITLE>I. 회사의 개요</TITLE>
     <SECTION-2><TITLE>1. 회사의 개요</TITLE><P>...</P><TABLE>...</TABLE></SECTION-2>
  </SECTION-1>
</BODY></DOCUMENT>
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

CELL_TAGS = {"td", "th", "te", "tu"}  # TE/TU = DART 전용 데이터 셀(입력형/선택형)


@dataclass
class Table:
    header: list[str]
    rows: list[list[str]]
    caption: str = ""
    unit: str = ""

    def to_markdown(self, max_rows: int | None = None) -> str:
        rows = self.rows if max_rows is None else self.rows[:max_rows]
        w = max([len(self.header)] + [len(r) for r in rows]) if (rows or self.header) else 0
        pad = lambda r: (r + [""] * w)[:w]
        lines = []
        if self.caption or self.unit:
            cap = f"**{self.caption}** " if self.caption else ""
            lines.append(f"{cap}{('(단위: ' + self.unit + ')') if self.unit else ''}".strip())
        hdr = pad(self.header) if self.header else [f"col{i+1}" for i in range(w)]
        lines.append("| " + " | ".join(hdr) + " |")
        lines.append("|" + "---|" * w)
        for r in rows:
            lines.append("| " + " | ".join(pad(r)) + " |")
        return "\n".join(lines)


@dataclass
class Block:
    """섹션 안의 순서 있는 콘텐츠 블록 (문단 or 표)."""
    kind: str  # "text" | "table"
    text: str = ""
    table: Table | None = None


@dataclass
class Section:
    title: str
    level: int
    blocks: list[Block] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)
    parent: "Section | None" = field(default=None, repr=False)

    @property
    def path(self) -> list[str]:
        node, out = self, []
        while node is not None and node.level > 0:
            out.append(node.title)
            node = node.parent
        return list(reversed(out))

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def plain_text(self) -> str:
        return "\n".join(b.text for b in self.blocks if b.kind == "text")


# ----------------------------------------------------------------------------------
def _clean(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


def _norm_title(t: str) -> str:
    return _clean(re.sub(r"\s+", " ", t))


def parse_table(tbl: Tag) -> Table:
    caption = ""
    unit = ""
    # 표 바로 앞 문단의 "(단위 : 백만원)" 캡처
    prev = tbl.find_previous_sibling()
    if prev is not None and prev.name in {"p", "table-group", "div"}:
        m = re.search(r"단위\s*[:：]\s*([^)\]）]+)", prev.get_text(" "))
        if m:
            unit = m.group(1).strip()
    # --- rowspan/colspan 을 반영한 그리드 전개 ---
    trs = [tr for tr in tbl.find_all("tr") if tr.find_parent("table") is tbl]
    grid: list[list[str]] = []
    is_head: list[bool] = []
    pending: dict[int, tuple[str, int]] = {}  # col -> (value, remaining rows)
    for tr in trs:
        cells = [c for c in tr.find_all(list(CELL_TAGS)) if c.find_parent("tr") is tr]
        row: list[str] = []
        col = 0
        ci = 0
        while ci < len(cells) or any(r > 0 for _, r in pending.values() if col in pending):
            if col in pending and pending[col][1] > 0:
                v, r = pending[col]
                row.append(v)
                pending[col] = (v, r - 1)
                col += 1
                continue
            if ci >= len(cells):
                break
            c = cells[ci]; ci += 1
            txt = _clean(c.get_text(" "))
            cs = int(c.get("colspan", 1) or 1)
            rs = int(c.get("rowspan", 1) or 1)
            for k in range(cs):
                row.append(txt)
                if rs > 1:
                    pending[col + k] = (txt, rs - 1)
            col += cs
        # 남은 rowspan 셀 보정 (행 마지막에 위치한 경우)
        while col in pending and pending[col][1] > 0:
            v, r = pending[col]; row.append(v); pending[col] = (v, r - 1); col += 1
        if not any(row):
            continue
        grid.append(row)
        is_head.append(tr.find_parent("thead") is not None or (bool(cells) and all(c.name == "th" for c in cells)))

    # --- 헤더: 연속된 선행 헤더행들을 "상위 / 하위" 로 병합 ---
    n_head = 0
    while n_head < len(grid) and is_head[n_head]:
        n_head += 1
    if n_head == 0 and len(grid) > 1:
        n_head = 1  # THEAD 없으면 첫 행을 헤더로
    header: list[str] = []
    if n_head:
        width = max(len(r) for r in grid[:n_head])
        for j in range(width):
            parts = []
            for r in grid[:n_head]:
                v = r[j] if j < len(r) else ""
                if v and (not parts or parts[-1] != v):
                    parts.append(v)
            header.append(" / ".join(parts))
    rows = grid[n_head:]
    return Table(header=header, rows=rows, caption=caption, unit=unit)


def table_is_textual(t: Table) -> bool:
    """DART 주석/설명문을 1열 표로 감싼 경우 → 본문 텍스트로 처리."""
    allrows = ([t.header] if t.header else []) + t.rows
    if all(len([v for v in set(r) if v]) <= 1 for r in allrows):
        return True
    # '(기준일 : 2023년 12월 31일)' 식 루버트 1행 표: 수치(천단위 콤마/소수) 가 없으면 본문 처리
    if len(t.rows) <= 1:
        joined = " ".join(v for r in allrows for v in r)
        return not re.search(r"\d{1,3}(?:,\d{3})+|\d+\.\d+|\b\d{4,}\b(?!\s*년)", joined)
    return False


CONTAINER_TAGS = {"body", "document", "part", "div", "table-group", "library", "html"}


def _has_section(tag: Tag) -> bool:
    return tag.find(lambda t: t.name and t.name.lower().startswith("section")) is not None


def _collect_blocks(node: Tag, sec: Section) -> None:
    """섹션 직속 자식 중 SECTION 제외한 콘텐츠를 순서대로 블록화."""
    for ch in node.children:
        if not isinstance(ch, Tag):
            txt = _clean(str(ch))
            if txt:
                sec.blocks.append(Block("text", txt))
            continue
        name = ch.name.lower()
        if name.startswith("section"):
            continue
        if name == "title":
            continue
        if name == "table":
            t = parse_table(ch)
            if not (t.rows or t.header):
                continue
            if table_is_textual(t):
                # 1열 표 = 설명문/단위표기 → 텍스트 보족으로 강드면 바로 뒤 표의 단위로 이어줌
                txt = "\n".join(next((v for v in r if v), "") for r in ([t.header] if t.header else []) + t.rows)
                m = re.search(r"단위\s*[:：]\s*([^)\]）]+)", txt)
                if m:
                    sec._pending_unit = m.group(1).strip()
                if txt.strip():
                    sec.blocks.append(Block("text", txt.strip()))
                continue
            if not t.unit and getattr(sec, "_pending_unit", ""):
                t.unit = sec._pending_unit
            sec._pending_unit = ""
            sec.blocks.append(Block("table", table=t))
        elif name in CONTAINER_TAGS or _has_section(ch) or ch.find("table") is not None:
            _collect_blocks(ch, sec)
        else:
            txt = _clean(ch.get_text(" "))
            if txt:
                m = re.search(r"단위\s*[:：]\s*([^)\]）]+)", txt)
                if m:
                    sec._pending_unit = m.group(1).strip()
                sec.blocks.append(Block("text", txt))


def _build(node: Tag, parent: Section) -> None:
    for ch in node.children:
        if not isinstance(ch, Tag):
            continue
        name = ch.name.lower()
        if name.startswith("section"):
            m = re.match(r"section-?(\d+)", name)
            level = int(m.group(1)) if m else parent.level + 1
            title_tag = ch.find("title", recursive=False) or ch.find("title")
            title = _norm_title(title_tag.get_text(" ")) if title_tag else "(제목 없음)"
            sec = Section(title=title, level=level, parent=parent)
            parent.children.append(sec)
            _collect_blocks(ch, sec)
            _build(ch, sec)
        elif name in CONTAINER_TAGS or _has_section(ch):
            # 섹션이 아닌 컨테이너(LIBRARY, PART, DIV …): 하위 섹션 계속 탐색
            _build(ch, parent)


def parse_dart_xml(xml: str) -> Section:
    xml = re.sub(r"&(cr|crlf|nbsp);", " ", xml)          # DART 커스텀 엔티티
    xml = re.sub(r"<\?xml[^>]*\?>", "", xml)
    soup = BeautifulSoup(xml, "lxml")
    root = Section(title="ROOT", level=0)
    body = soup.find("body") or soup
    _build(body, root)
    # 섹션 밖에 떠 있는 표지/개요 텍스트도 보존
    if not root.children:
        _collect_blocks(body, root)
    return root


def print_toc(root: Section, max_level: int = 2) -> str:
    lines = []
    for s in root.walk():
        if 0 < s.level <= max_level:
            n_tbl = sum(1 for b in s.blocks if b.kind == "table")
            lines.append("  " * (s.level - 1) + f"- {s.title}  [text {len(s.plain_text())}자, 표 {n_tbl}개]")
    return "\n".join(lines)
