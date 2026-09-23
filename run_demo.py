"""여러 질문을 한 번에 실행해 결과를 demo_results.md 로 저장."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass
from dart_rag.store import VectorStore
from dart_rag.wiki import WikiBuilder
from dart_rag.rag import DartRAG

QUESTIONS = [
    "2023년 사업보고서 기준 연결 매출액과 영업이익은 얼마이고, 전년 대비 얼마나 변했어?",
    "2024년 3분기 누적 DS부문 매출은 얼마이고 전년 동기 대비 몇 % 증가했어?",
    "2023년 말 기준 직원 수와 1인 평균 급여액은?",
    "2023년 연구개발비 총액과 매출액 대비 비율은?",
    "2023년 보통주 1주당 배당금과 연간 배당총액은?",
    "2024년 상반기 기준 삼성전자 최대주주와 지분율은?",
    "2023년 사업보고서에 나온 DS부문 주요 제품은 뭐야?",
]

rag = DartRAG(VectorStore(), WikiBuilder())
out = [f"# DART RAG 데모 결과\n\nLLM backend: {rag.backend} / {rag.model}\n"]
for q in QUESTIONS:
    t = time.time()
    a = rag.ask(q, k=6)
    out.append(f"\n## Q. {q}\n\n필터: `{a.filters}` · {time.time()-t:.1f}s\n\n{a.answer}\n\n**출처**\n")
    out += [f"- [{s['n']}] {s['source']} ({s['kind']})" for s in a.sources[:4]]
    print(f"done: {q[:40]}  ({time.time()-t:.1f}s)", flush=True)
Path("demo_results.md").write_text("\n".join(out), "utf-8")
