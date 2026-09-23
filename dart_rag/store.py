"""벡터 스토어 + 하이브리드 검색.

- Embedder: OpenAI(text-embedding-3-small) 가 기본. 키 없으면 HashingEmbedder(char n-gram, 로컬) 로 폴백.
- VectorStore: numpy 행렬 + jsonl 메타 (Chroma/pgvector/Qdrant 로 교체 시 이 클래스만 바꾸면 됨).
- Hybrid: 코사인(dense) + BM25(sparse, 한국어 char-bigram+숫자 토큰) 을 RRF 로 융합.
  공시 질의는 "제55기", "2023년", "매출액" 등 정확 토큰 매칭이 중요해 sparse 가 크게 기여.
- 메타 필터: report_type / period / tags / kind 등으로 사전 필터.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from .chunker import Chunk


# ------------------------------- tokenizer --------------------------------
def tokenize(text: str) -> list[str]:
    text = text.lower()
    toks = []
    for w in re.findall(r"[가-힣]+|[a-z]+|\d[\d,\.]*", text):
        if re.match(r"\d", w):
            toks.append(w.replace(",", ""))
        elif re.match(r"[가-힣]", w):
            toks.append(w)
            toks += [w[i:i + 2] for i in range(len(w) - 1)]  # char bigram (조사 영향 완화)
        else:
            toks.append(w)
    return toks


# ------------------------------- embedders --------------------------------
class HashingEmbedder:
    """외부 API 없이 동작하는 폴백. char n-gram 해싱 → L2 정규화 (품질은 BM25 보조 수준)."""
    name = "hashing-ngram-1024"
    dim = 1024

    def embed(self, texts: list[str]) -> np.ndarray:
        M = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokenize(t):
                h = int(hashlib.blake2b(tok.encode(), digest_size=4).hexdigest(), 16) % self.dim
                M[i, h] += 1.0
        M = np.log1p(M)
        n = np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
        return M / n


class OpenAIEmbedder:
    name = "text-embedding-3-small"
    dim = 1536

    def __init__(self, model: str | None = None):
        from openai import OpenAI
        self.client = OpenAI()
        self.name = model or os.environ.get("EMBED_MODEL", self.name)

    def embed(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), 100):
            batch = [t[:8000] for t in texts[i:i + 100]]
            r = self.client.embeddings.create(model=self.name, input=batch)
            out += [d.embedding for d in r.data]
        M = np.asarray(out, dtype=np.float32)
        return M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)


def get_embedder():
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIEmbedder()
    return HashingEmbedder()


# ------------------------------- store ------------------------------------
class VectorStore:
    def __init__(self, path: str = "data/vectordb", embedder=None):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or get_embedder()
        self.chunks: list[Chunk] = []
        self.vecs: np.ndarray | None = None
        self._bm25 = None
        self._load()

    # persistence ---------------------------------------------------------
    def _load(self):
        meta = self.path / "chunks.jsonl"
        vec = self.path / "vectors.npy"
        info = self.path / "info.json"
        if meta.exists() and vec.exists():
            if info.exists() and json.loads(info.read_text()).get("embedder") != self.embedder.name:
                print("[store] 임베더가 달라 기존 인덱스를 무시합니다.")
                return
            self.chunks = [Chunk(**json.loads(l)) for l in meta.read_text("utf-8").splitlines() if l]
            self.vecs = np.load(vec)
            self._build_bm25()

    def _save(self):
        with (self.path / "chunks.jsonl").open("w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        np.save(self.path / "vectors.npy", self.vecs)
        (self.path / "info.json").write_text(json.dumps({"embedder": self.embedder.name, "n": len(self.chunks)}))

    def _build_bm25(self):
        self._bm25 = BM25Okapi([tokenize(c.text) for c in self.chunks]) if self.chunks else None

    # write ---------------------------------------------------------------
    def add(self, chunks: list[Chunk]):
        have = {c.id for c in self.chunks}
        new = [c for c in chunks if c.id not in have]
        if not new:
            return 0
        V = self.embedder.embed([c.text for c in new])
        self.vecs = V if self.vecs is None else np.vstack([self.vecs, V])
        self.chunks += new
        self._build_bm25()
        self._save()
        return len(new)

    # read ----------------------------------------------------------------
    def _mask(self, where: dict | None) -> np.ndarray:
        m = np.ones(len(self.chunks), dtype=bool)
        if not where:
            return m
        for i, c in enumerate(self.chunks):
            for k, v in where.items():
                if k == "period_year":
                    cv = c.meta.get("period", "")[:4]
                else:
                    cv = c.meta.get(k) if k != "kind" else c.kind
                ok = (v in cv) if isinstance(cv, list) else (cv in v if isinstance(v, (list, tuple, set)) else cv == v)
                if not ok:
                    m[i] = False
                    break
        return m

    def search(self, query: str, k: int = 8, where: dict | None = None, alpha_rrf: int = 60) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        mask = self._mask(where)
        idx = np.where(mask)[0]
        if len(idx) == 0:
            return []
        q = self.embedder.embed([query])[0]
        dense = self.vecs[idx] @ q
        sparse = np.asarray(self._bm25.get_scores(tokenize(query)))[idx]
        # RRF 융합
        d_rank = np.argsort(-dense)
        s_rank = np.argsort(-sparse)
        score = np.zeros(len(idx))
        for r, i in enumerate(d_rank):
            score[i] += 1 / (alpha_rrf + r)
        for r, i in enumerate(s_rank):
            score[i] += 1 / (alpha_rrf + r)
        # (1) 내용이 거의 없는 청크 패널터 (2) 수치 KV 가산
        # (3) 섹션 제목 부스트: 질문 토큰이 섹션 경로(예: '6. 배당에 관한 사항')에 등장하면 크게 가산.
        #     공시는 목차가 표준화되어 있어 제목 매칭이 가장 강한 라우팅 신호이고,
        #     주석(수백 개 표)이 본문 섹션을 묻는 문제를 완화함.
        q_toks = {t for t in tokenize(query) if len(t) >= 2 and not t.isdigit()}
        for j, i in enumerate(idx):
            c = self.chunks[i]
            raw = c.meta.get("raw", c.text)
            if len(raw) < 80:
                score[j] *= 0.5
            if c.kind == "table_kv":
                score[j] *= 1.1
            if q_toks:
                title_toks = set(tokenize(c.meta.get("section_path", "")))
                ov = len(q_toks & title_toks) / len(q_toks)
                score[j] *= 1 + 1.5 * ov
            if "주석" in c.meta.get("section_title", "") and "주석" not in query:
                score[j] *= 0.8  # 주석 표는 질문이 명시하지 않으면 본문 섹션보다 후순위
        top = np.argsort(-score)[:k]
        return [(self.chunks[idx[i]], float(score[i])) for i in top]
