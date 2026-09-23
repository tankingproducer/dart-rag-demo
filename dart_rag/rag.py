"""검색 → 컨텍스트 조립 → LLM 답변 (출처 인용).

- 질의 라우팅: 질문에서 연도/보고서 종류를 추출해 메타 필터로 좁힘 (예: "2023년 사업보고서")
- small-to-big: table_kv 가 걸리면 같은 표(table) 청크를 함께 컨텍스트에 포함
- LLM: OpenAI(OPENAI_API_KEY) 사용. 키 없으면 추출식 폴백(상위 청크 그대로 제시).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .store import VectorStore
from .wiki import WikiBuilder

SYSTEM = """당신은 한국 상장회사의 DART 공시(사업보고서·분기보고서) 전문 애널리스트입니다.
아래 [컨텍스트] 에 제공된 공시 발췌만을 근거로 답하세요.
규칙:
1. 수치는 컨텍스트에 있는 값·단위·기수(제N기)·기간을 그대로 인용하고, 반드시 출처 번호 [n] 를 붙입니다.
2. 컨텍스트에 없는 내용은 추측하지 말고 "제공된 공시 발췌에서 확인되지 않습니다" 라고 말합니다.
3. 여러 보고서(기간)가 섞여 있으면 어느 보고서 기준인지 명시합니다.
4. 표 데이터는 필요하면 간단한 표로 재정리합니다. 답변은 한국어로 간결하게."""


@dataclass
class Answer:
    question: str
    answer: str
    sources: list[dict]
    filters: dict


def infer_filters(q: str) -> dict:
    """질문 → 메타 필터. 예) '2023년 사업보고서' → {report_type: 사업보고서, period: 2023.12}
    '2024년 3분기' → {report_type: 분기보고서, period: 2024.09}"""
    f = {}
    year = re.search(r"(20\d{2})\s*년?", q)
    y = year.group(1) if year else None
    quarter = re.search(r"([1-4])\s*분기", q)
    if "사업보고서" in q or re.search(r"연간|년\s*말|연말|기말", q):
        f["report_type"] = "사업보고서"
        if y:
            f["period"] = f"{y}.12"
    elif "반기" in q or (quarter and quarter.group(1) == "2"):
        f["report_type"] = "반기보고서"
        if y:
            f["period"] = f"{y}.06"
    elif "분기보고서" in q or quarter:
        f["report_type"] = "분기보고서"
        if y and quarter:
            f["period"] = f"{y}.{'03' if quarter.group(1) == '1' else '09'}"
    elif y:
        f["period_year"] = y  # 보고서 종류 미지정: 해당 연도 보고서 전체
    return f


class DartRAG:
    def __init__(self, store: VectorStore, wiki: WikiBuilder | None = None, model: str | None = None):
        self.store = store
        self.wiki = wiki
        self.llm = None
        self.model = model or os.environ.get("LLM_MODEL")
        # LLM 백엔드 우선순위: Groq(무료, Llama 3.3 70B) → OpenAI → 없음(추출식 폴백)
        if os.environ.get("GROQ_API_KEY"):
            from openai import OpenAI
            self.llm = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url="https://api.groq.com/openai/v1")
            self.model = self.model or os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")  # 대안: qwen/qwen3.8-27b
        elif os.environ.get("OPENAI_API_KEY"):
            from openai import OpenAI
            self.llm = OpenAI()
            self.model = self.model or "gpt-4o-mini"
        self.backend = "groq" if os.environ.get("GROQ_API_KEY") else ("openai" if self.llm else "none")

    per_chunk_chars = 1800
    max_ctx_chars = 9000   # ≈ 5~6k 토큰(한글·숫자 혼합 기준)

    def _complete(self, user: str, retries: int = 3) -> str:
        import time
        from openai import RateLimitError, APIStatusError
        for i in range(retries):
            try:
                r = self.llm.chat.completions.create(
                    model=self.model, temperature=0, max_tokens=2500,  # gpt-oss 는 reasoning 토큰도 포함
                    messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                    extra_body={"reasoning_effort": "low"} if "gpt-oss" in self.model else {})
                return r.choices[0].message.content
            except (RateLimitError, APIStatusError) as e:
                if getattr(e, "status_code", 0) not in (413, 429) or i == retries - 1:
                    raise
                wait = 20 * (i + 1)
                print(f"  [rate-limit] {wait}s 대기 후 재시도")
                time.sleep(wait)

    def retrieve(self, q: str, k: int = 8, where: dict | None = None):
        where = {**infer_filters(q), **(where or {})}
        hits = self.store.search(q, k=k, where=where)
        if not hits and where:  # 필터가 과하면 완화
            hits = self.store.search(q, k=k)
        # 섹션 확장: 상위 3개 섹션의 표 KV 청크 중 질문과 가장 잘 맞는 것을 동반
        #   (예: '배당' 섹션 본문이 잌히면 같은 섹션의 배당금 표도 컨텍스트에 포함)
        from .store import tokenize
        ids = {c.id for c, _ in hits}
        seen_parents, sib = [], []
        qt = set(tokenize(q))
        for c, s in hits:
            p = c.meta["parent_id"]
            if p in seen_parents or len(seen_parents) >= 3:
                continue
            seen_parents.append(p)
            cands = [o for o in self.store.chunks if o.meta.get("parent_id") == p and o.kind == "table_kv" and o.id not in ids]
            cands.sort(key=lambda o: -len(qt & set(tokenize(o.meta.get("raw", "")))))
            for o in cands[:2]:
                sib.append((o, s * 0.95)); ids.add(o.id)
        hits = hits + sib
        # small-to-big: kv 청크 → 원본 표 청크 동반
        extra = []
        for c, s in hits:
            if c.kind == "table_kv":
                for o in self.store.chunks:
                    if o.kind == "table" and o.meta.get("parent_id") == c.meta["parent_id"] \
                            and o.meta.get("table_index") == c.meta.get("table_index") \
                            and o.meta.get("row_start") == c.meta.get("row_start") and o.id not in ids:
                        extra.append((o, s * 0.99)); ids.add(o.id)
        return hits + extra, where

    def ask(self, q: str, k: int = 8, where: dict | None = None) -> Answer:
        hits, filters = self.retrieve(q, k, where)
        ctx_parts, sources = [], []
        for i, (c, s) in enumerate(hits, 1):
            m = c.meta
            src = f"{m['corp_name']} {m['report_type']}({m['period']}) · {m['section_path']}"
            ctx_parts.append(f"[{i}] ({src})\n{c.meta.get('raw', c.text)}")
            sources.append({"n": i, "source": src, "kind": c.kind, "chunk_id": c.id, "score": round(s, 4),
                            "rcept_no": m["rcept_no"]})
        # 컨텍스트 예산: 개별 발췌 ≤ per_chunk 자, 전체 ≤ max_ctx 자 (Groq 무료티어 8k TPM 대응)
        per_chunk, max_ctx = self.per_chunk_chars, self.max_ctx_chars
        trimmed, total = [], 0
        for p in ctx_parts:
            p = p if len(p) <= per_chunk else p[:per_chunk] + "\n...(중략)"
            if total + len(p) > max_ctx:
                break
            trimmed.append(p); total += len(p)
        context = "\n\n".join(trimmed)
        if self.llm is None:
            ans = "(LLM 키 없음 → 추출식 폴백) 관련 발췌 상위:\n\n" + "\n\n".join(ctx_parts[:3])
        else:
            ans = self._complete(f"[컨텍스트]\n{context}\n\n[질문]\n{q}")
        return Answer(q, ans, sources, filters)
