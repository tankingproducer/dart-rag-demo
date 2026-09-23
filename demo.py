"""DART RAG 데모 CLI.

python demo.py ingest --corp 삼성전자 --from 20230101 --to 20241231   # 실데이터 (OPENDART_API_KEY 필요)
python demo.py ingest --sample                                          # 합성 샘플로 파이프라인 검증
python demo.py ask "2023년 사업보고서 기준 연결 매출액은?"
python demo.py chat                                                     # 대화형
python demo.py toc <rcept_no>                                           # 파싱된 목차 확인
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:  # .env 자동 로드 (있으면)
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass
from dart_rag.parser import parse_dart_xml, print_toc
from dart_rag.chunker import DartChunker
from dart_rag.wiki import WikiBuilder
from dart_rag.store import VectorStore
from dart_rag.rag import DartRAG


def ingest_xml(xml: str, doc_meta: dict, store: VectorStore, wiki: WikiBuilder, chunker: DartChunker):
    root = parse_dart_xml(xml)
    chunks = chunker.chunk_report(root, doc_meta)
    n = store.add(chunks)
    wiki.add_report(root, doc_meta, chunks)
    kinds = {}
    for c in chunks:
        kinds[c.kind] = kinds.get(c.kind, 0) + 1
    print(f"  ✔ {doc_meta['report_type']} {doc_meta['period']} (rcept {doc_meta['rcept_no']}): "
          f"섹션 {sum(1 for _ in root.walk()) - 1}개, 청크 {len(chunks)}개 {kinds}, 신규 저장 {n}")
    return root


def cmd_ingest(a):
    chunker = DartChunker()
    store = VectorStore()
    wiki = WikiBuilder()
    print(f"[embedder] {store.embedder.name}")
    if a.sample:
        from sample_data import SAMPLES
        for meta, xml in SAMPLES:
            ingest_xml(xml, meta, store, wiki, chunker)
        return
    from dart_rag.dart_client import DartClient
    cli = DartClient()
    code = cli.corp_code(a.corp)
    print(f"[corp_code] {a.corp} = {code}")
    filings = cli.list_filings(code, a.from_, a.to)
    if a.skip_amend:
        filings = [f for f in filings if "정정" not in f.report_nm]
    print(f"[filings] {len(filings)}건")
    for f in filings[: a.limit]:
        xml = cli.fetch_document_xml(f.rcept_no)
        meta = {"corp_name": f.corp_name, "report_type": f.report_type, "period": f.period,
                "rcept_no": f.rcept_no, "rcept_dt": f.rcept_dt, "report_nm": f.report_nm}
        ingest_xml(xml, meta, store, wiki, chunker)


def cmd_ask(a):
    rag = DartRAG(VectorStore(), WikiBuilder())
    ans = rag.ask(a.question, k=a.k)
    print(f"\n질문: {ans.question}\n필터: {ans.filters}\n\n답변:\n{ans.answer}\n\n출처:")
    for s in ans.sources:
        print(f"  [{s['n']}] {s['source']} ({s['kind']}, score={s['score']})")


def cmd_chat(a):
    rag = DartRAG(VectorStore(), WikiBuilder())
    print("질문을 입력하세요 (quit 종료)")
    while True:
        q = input("\n> ").strip()
        if q in {"quit", "exit", ""}:
            break
        ans = rag.ask(q)
        print(ans.answer)
        for s in ans.sources[:5]:
            print(f"  [{s['n']}] {s['source']}")


def cmd_toc(a):
    xml = Path(f"data/raw/{a.rcept_no}.xml").read_text("utf-8")
    print(print_toc(parse_dart_xml(xml), max_level=a.level))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd", required=True)
    i = sp.add_parser("ingest"); i.add_argument("--corp", default="삼성전자"); i.add_argument("--from", dest="from_", default="20230101")
    i.add_argument("--to", default="20241231"); i.add_argument("--limit", type=int, default=20); i.add_argument("--sample", action="store_true")
    i.add_argument("--skip-amend", action="store_true", help="[기재정정] 공시 제외"); i.set_defaults(fn=cmd_ingest)
    q = sp.add_parser("ask"); q.add_argument("question"); q.add_argument("-k", type=int, default=8); q.set_defaults(fn=cmd_ask)
    c = sp.add_parser("chat"); c.set_defaults(fn=cmd_chat)
    t = sp.add_parser("toc"); t.add_argument("rcept_no"); t.add_argument("--level", type=int, default=2); t.set_defaults(fn=cmd_toc)
    a = p.parse_args(); a.fn(a)
