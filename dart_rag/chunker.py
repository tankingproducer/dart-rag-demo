"""청킹 로직 (DART 공시 특화).

설계 원칙
---------
1. **계층 breadcrumb 컨텍스트 주입**: 모든 청크 앞에
   `[삼성전자 | 사업보고서 2023.12 | II. 사업의 내용 > 4. 매출 및 수주상황]` 를 붙여
   임베딩이 "어느 회사·어느 보고서·어느 섹션" 인지 알도록 함 (정보 손실 방지).
2. **섹션 = 청크 경계**: 서로 다른 섹션의 텍스트는 절대 한 청크에 섞지 않음.
   긴 섹션은 문단 단위로 누적 → target_chars 초과 시 분할, overlap 문단 유지.
3. **표는 별도 청킹**: 표를 텍스트에 섞어 자르면 열/행 정합성이 깨짐.
   - 표 헤더를 모든 표 청크에 반복 삽입 (header repetition)
   - 행 N개씩 묶음(row-group) 으로 분할
   - 각 행을 "항목=값" 형태 문장으로 선형화한 `kv_text` 도 생성 → 수치 질문에 강함
     예) "매출액(제55기)=258,935,494 백만원; 매출액(제54기)=302,231,360 백만원"
4. **메타데이터 풍부화**: corp, report_type, period, rcept_no, section_path, chunk_kind,
   table_caption, unit → 필터 검색(예: 2023 사업보고서만) 가능.
5. **부모-자식 연결**: 청크에 `parent_id`(섹션 위키 페이지 id) 보관 →
   검색은 작은 청크로, 답변 컨텍스트는 필요 시 부모 섹션으로 확장(small-to-big).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict

from .parser import Section, Table

# 삼성전자 사업보고서에서 자주 등장하는 핵심 섹션 → 위키 카테고리 태그
SECTION_TAGS = [
    (r"회사의 개요|연혁|자본금|주식의 총수|정관", "company"),
    (r"사업의 개요|주요 제품|원재료|생산|매출|수주|위험관리|파생|연구개발|기타 참고", "business"),
    (r"재무에 관한|요약재무|연결재무|재무제표|주석|배당|증권의 발행", "financial"),
    (r"이사회|감사제도|주주총회|의결권", "governance"),
    (r"임원|직원|보수", "people"),
    (r"주주에 관한|최대주주|소액주주", "shareholder"),
    (r"계열회사|타법인출자", "affiliates"),
    (r"이해관계자|대주주.*거래|제재|소송", "related"),
]


def tag_section(path: list[str]) -> list[str]:
    joined = " ".join(path)
    return [t for pat, t in SECTION_TAGS if re.search(pat, joined)] or ["etc"]


@dataclass
class Chunk:
    id: str
    text: str            # 임베딩 대상 (breadcrumb 포함)
    kind: str            # "text" | "table" | "table_kv"
    meta: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _cid(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:16]


def _split_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    out = []
    for p in paras:  # 매우 긴 문단은 문장 단위로 추가 분할
        if len(p) <= 800:
            out.append(p)
            continue
        for s in re.split(r"(?<=[.다\.]\s)", p):
            s = s.strip()
            if not s:
                continue
            # 문장 경계가 없는 초장문(리스트 나열 등)은 고정 길이로 강제 분할
            out.extend(s[i:i + 800] for i in range(0, len(s), 800))
    return out


class DartChunker:
    def __init__(self, target_chars: int = 900, max_chars: int = 1400,
                 overlap_paras: int = 1, table_rows_per_chunk: int = 12, max_cols: int = 10,
                 hard_cap: int = 6000, table_chars: int = 1400):
        self.target = target_chars
        self.max = max_chars
        self.overlap = overlap_paras
        self.rows_per = table_rows_per_chunk
        self.max_cols = max_cols
        self.hard_cap = hard_cap  # 임베딩 토큰 한도 보호용 상한
        self.table_chars = table_chars  # 표 row-group 하나의 KV 글자 예산

    # ------------------------------------------------------------------
    def chunk_report(self, root: Section, doc_meta: dict) -> list[Chunk]:
        """doc_meta: corp_name, report_type, period, rcept_no, rcept_dt"""
        chunks: list[Chunk] = []
        for sec in root.walk():
            if sec.level == 0 and not sec.blocks:
                continue
            path = sec.path or ["표지"]
            crumb = f"[{doc_meta['corp_name']} | {doc_meta['report_type']} {doc_meta['period']} | {' > '.join(path)}]"
            page_id = _cid(doc_meta["rcept_no"], *path)
            base_meta = {
                **doc_meta,
                "section_path": " > ".join(path),
                "section_title": path[-1],
                "section_level": sec.level,
                "tags": tag_section(path),
                "parent_id": page_id,
            }
            chunks += self._chunk_text_blocks(sec, crumb, base_meta)
            t_idx = 0
            for b in sec.blocks:
                if b.kind == "table" and b.table:
                    chunks += self._chunk_table(b.table, t_idx, crumb, base_meta)
                    t_idx += 1
        return chunks

    # ------------------------------------------------------------------
    def _chunk_text_blocks(self, sec: Section, crumb: str, meta: dict) -> list[Chunk]:
        paras = _split_paragraphs(sec.plain_text())
        if not paras:
            return []
        out, buf, buf_len, idx = [], [], 0, 0

        def flush():
            nonlocal buf, buf_len, idx
            if not buf:
                return
            body = "\n".join(buf)
            cid = _cid(meta["rcept_no"], meta["section_path"], "text", str(idx))
            out.append(Chunk(cid, f"{crumb}\n{body}", "text", {**meta, "chunk_index": idx, "raw": body}))
            idx += 1
            keep = buf[-self.overlap:] if self.overlap else []
            buf, buf_len = list(keep), sum(len(p) for p in keep)

        for p in paras:
            if buf and buf_len + len(p) > self.target:
                flush()
            buf.append(p)
            buf_len += len(p)
            if buf_len > self.max:
                flush()
        flush()
        return out

    # ------------------------------------------------------------------
    def _chunk_table(self, t: Table, t_idx: int, crumb: str, meta: dict) -> list[Chunk]:
        # 너무 넓은 표(예: 종속기업 200개가 열로) → 첫 열(라벨) 고정 + 열 그룹으로 분할
        width = max([len(t.header)] + [len(r) for r in t.rows]) if (t.header or t.rows) else 0
        if width > self.max_cols:
            out = []
            for ci, cs in enumerate(range(1, width, self.max_cols - 1)):
                cols = [0] + list(range(cs, min(cs + self.max_cols - 1, width)))
                pick = lambda r: [r[j] if j < len(r) else "" for j in cols]
                sub = Table(header=pick(t.header) if t.header else [], rows=[pick(r) for r in t.rows],
                            caption=t.caption, unit=t.unit)
                out += self._chunk_table_rows(sub, t_idx, crumb, meta, col_group=ci)
            return out
        return self._chunk_table_rows(t, t_idx, crumb, meta)

    def _chunk_table_rows(self, t: Table, t_idx: int, crumb: str, meta: dict, col_group: int = 0) -> list[Chunk]:
        out = []
        hdr = t.header
        # 행 범위를 고정 N행이 아니라 "글자 예산" 기준으로 가변 묶음 (넓은 표는 적은 행, 좁은 표는 많은 행)
        groups, cur, cur_len = [], [], 0
        for r in t.rows:
            rl = sum(len(v) + len(h) + 4 for h, v in zip(hdr, r)) + 20
            if cur and (cur_len + rl > self.table_chars or len(cur) >= self.rows_per):
                groups.append(cur); cur, cur_len = [], 0
            cur.append(r); cur_len += rl
        groups.append(cur)
        start = 0
        for g, rows in enumerate(groups):
            sub = Table(header=hdr, rows=rows, caption=t.caption, unit=t.unit)
            g = f"{col_group}-{g}"
            md = sub.to_markdown()
            tmeta = {**meta, "table_index": t_idx, "row_start": start, "col_group": col_group, "unit": t.unit,
                     "table_header": " / ".join(hdr)[:300]}
            cid = _cid(meta["rcept_no"], meta["section_path"], f"table{t_idx}", g)
            out.append(Chunk(cid, f"{crumb}\n(표 {t_idx + 1}, 행 {start + 1}-{start + len(rows)})\n{md}",
                             "table", {**tmeta, "raw": md[:self.hard_cap]}))
            # 행 선형화(KV) 청크: 수치 질의 대응 (표가 수치를 한 개라도 포함할 때만)
            kv = self._linearize(sub)
            if kv and re.search(r"\d", kv):
                out.append(Chunk(_cid(cid, "kv"), f"{crumb}\n{kv[:self.hard_cap]}", "table_kv", {**tmeta, "raw": kv[:self.hard_cap]}))
            start += len(rows)
        return out

    @staticmethod
    def _linearize(t: Table) -> str:
        if not t.header or not t.rows:
            return ""
        unit = f" {t.unit}" if t.unit else ""
        lines = []
        for r in t.rows:
            label = r[0] if r else ""
            pairs = []
            for h, v in zip(t.header[1:], r[1:]):
                if v and h:
                    pairs.append(f"{label}({h})={v}{unit if re.search(r'\d', v) else ''}")
            if pairs:
                lines.append("; ".join(pairs))
        return "\n".join(lines)
