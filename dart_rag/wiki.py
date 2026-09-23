"""위키 형태 지식 구조.

wiki/
  index.json                         전체 페이지 인덱스(그래프: 노드+엣지)
  삼성전자/
    _company.md                      회사 허브 페이지 (보고서 목록·태그별 링크)
    사업보고서_2023.12/
      _report.md                     보고서 허브 (목차 → 섹션 페이지 링크)
      II-사업의-내용__4-매출-및-수주상황.md   섹션 페이지 (본문 + 표 + 관련 청크 id)
  _topics/
    financial.md                     태그(주제)별 크로스 리포트 페이지 (시계열 비교용)

각 섹션 페이지 = 청크의 parent (small-to-big 확장용). frontmatter 에 메타 보관.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .chunker import Chunk, _cid, tag_section
from .parser import Section


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\-가-힣.]+", "-", s).strip("-")
    return s[:80]


class WikiBuilder:
    def __init__(self, root: str = "wiki"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else {"nodes": {}, "edges": []}

    def _node(self, nid: str, **attrs):
        self.index["nodes"][nid] = {**self.index["nodes"].get(nid, {}), **attrs}

    def _edge(self, a: str, b: str, rel: str):
        e = {"from": a, "to": b, "rel": rel}
        if e not in self.index["edges"]:
            self.index["edges"].append(e)

    # ------------------------------------------------------------------
    def add_report(self, root_sec: Section, doc_meta: dict, chunks: list[Chunk]) -> None:
        corp, rtype, period = doc_meta["corp_name"], doc_meta["report_type"], doc_meta["period"]
        corp_dir = self.root / _slug(corp)
        rep_dir = corp_dir / _slug(f"{rtype}_{period}")
        rep_dir.mkdir(parents=True, exist_ok=True)

        corp_id = f"corp:{corp}"
        rep_id = f"report:{doc_meta['rcept_no']}"
        self._node(corp_id, type="company", title=corp, path=str(corp_dir / "_company.md"))
        self._node(rep_id, type="report", title=f"{corp} {rtype} ({period})", corp=corp, report_type=rtype,
                   period=period, rcept_no=doc_meta["rcept_no"], path=str(rep_dir / "_report.md"))
        self._edge(corp_id, rep_id, "has_report")

        by_parent: dict[str, list[Chunk]] = {}
        for c in chunks:
            by_parent.setdefault(c.meta["parent_id"], []).append(c)

        toc_lines = []
        for sec in root_sec.walk():
            if sec.level == 0:
                continue
            path = sec.path
            page_id = _cid(doc_meta["rcept_no"], *path)
            fname = _slug("__".join(path)) + ".md"
            fpath = rep_dir / fname
            tags = tag_section(path)
            sec_chunks = by_parent.get(page_id, [])
            body = self._render_section(sec, doc_meta, path, tags, sec_chunks, rep_dir.name)
            fpath.write_text(body, "utf-8")
            self._node(f"section:{page_id}", type="section", title=" > ".join(path), corp=corp, report_type=rtype,
                       period=period, rcept_no=doc_meta["rcept_no"], tags=tags, path=str(fpath),
                       n_chunks=len(sec_chunks), chunk_ids=[c.id for c in sec_chunks])
            self._edge(rep_id, f"section:{page_id}", "has_section")
            if sec.parent and sec.parent.level > 0:
                self._edge(f"section:{_cid(doc_meta['rcept_no'], *sec.parent.path)}", f"section:{page_id}", "child")
            for t in tags:
                self._edge(f"topic:{t}", f"section:{page_id}", "topic_of")
                self._node(f"topic:{t}", type="topic", title=t, path=str(self.root / "_topics" / f"{t}.md"))
            toc_lines.append("  " * (sec.level - 1) + f"- [{sec.title}]({fname})  `{','.join(tags)}`")

        (rep_dir / "_report.md").write_text(
            f"---\ntype: report\ncorp: {corp}\nreport_type: {rtype}\nperiod: {period}\nrcept_no: {doc_meta['rcept_no']}\n"
            f"rcept_dt: {doc_meta.get('rcept_dt','')}\n---\n# {corp} {rtype} ({period})\n\n"
            f"- 회사 페이지: [{corp}](../_company.md)\n- 청크 수: {len(chunks)}\n\n## 목차\n" + "\n".join(toc_lines) + "\n", "utf-8")
        self._write_company(corp, corp_dir)
        self._write_topics()
        self.index_path.write_text(json.dumps(self.index, ensure_ascii=False, indent=1), "utf-8")

    # ------------------------------------------------------------------
    def _render_section(self, sec, meta, path, tags, chunks, rep_dirname) -> str:
        fm = (f"---\ntype: section\ncorp: {meta['corp_name']}\nreport_type: {meta['report_type']}\n"
              f"period: {meta['period']}\nrcept_no: {meta['rcept_no']}\nsection_path: {' > '.join(path)}\n"
              f"tags: [{', '.join(tags)}]\nchunk_ids: [{', '.join(c.id for c in chunks)}]\n---\n")
        out = [fm, f"# {' > '.join(path)}", "",
               f"> 출처: {meta['corp_name']} {meta['report_type']} ({meta['period']}) · 접수번호 {meta['rcept_no']} · [보고서 목차](_report.md)", ""]
        # 상위/하위 링크
        if sec.parent and sec.parent.level > 0:
            out.append(f"⬆ 상위: [{sec.parent.title}]({_slug('__'.join(sec.parent.path))}.md)")
        if sec.children:
            out.append("⬇ 하위: " + " · ".join(f"[{c.title}]({_slug('__'.join(c.path))}.md)" for c in sec.children))
        out.append("")
        t_idx = 0
        for b in sec.blocks:
            if b.kind == "text":
                out.append(b.text)
                out.append("")
            elif b.table:
                t_idx += 1
                out.append(f"### 표 {t_idx}")
                out.append(b.table.to_markdown())
                out.append("")
        return "\n".join(out)

    def _write_company(self, corp: str, corp_dir: Path):
        reps = [n for n in self.index["nodes"].values() if n.get("type") == "report" and n.get("corp") == corp]
        reps.sort(key=lambda n: n["period"], reverse=True)
        lines = [f"---\ntype: company\ncorp: {corp}\n---", f"# {corp}", "", "## 보고서"]
        for r in reps:
            lines.append(f"- [{r['title']}]({Path(r['path']).parent.name}/_report.md)  접수번호 {r['rcept_no']}")
        lines += ["", "## 주제별", ""] + [f"- [{t}](../_topics/{t}.md)" for t in sorted(
            {t for n in self.index['nodes'].values() if n.get('type') == 'section' and n.get('corp') == corp for t in n['tags']})]
        (corp_dir / "_company.md").write_text("\n".join(lines) + "\n", "utf-8")

    def _write_topics(self):
        tdir = self.root / "_topics"
        tdir.mkdir(exist_ok=True)
        secs = [n for n in self.index["nodes"].values() if n.get("type") == "section"]
        for t in {t for n in secs for t in n["tags"]}:
            lines = [f"# 주제: {t}", "", "보고서 간 동일 섹션을 시계열로 비교할 때 사용.", ""]
            for n in sorted((s for s in secs if t in s["tags"]), key=lambda s: (s["title"], s["period"]), reverse=True):
                rel = Path(n["path"]).relative_to(self.root)
                lines.append(f"- [{n['corp']} {n['report_type']} {n['period']} · {n['title']}](../{rel})")
            (tdir / f"{t}.md").write_text("\n".join(lines) + "\n", "utf-8")

    # 부모 섹션 원문 조회 (small-to-big)
    def get_section_text(self, parent_id: str) -> str | None:
        n = self.index["nodes"].get(f"section:{parent_id}")
        if not n:
            return None
        return Path(n["path"]).read_text("utf-8")
