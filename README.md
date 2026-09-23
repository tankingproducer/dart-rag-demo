# DART 공시 RAG + 위키 지식구조 (삼성전자 데모)

OpenDART 원문(사업·반기·분기보고서) → 섹션 트리 파싱 → 공시 특화 청킹 → 위키 페이지 + 벡터DB → 하이브리드 검색 → LLM 답변(출처 인용)

---

## 1. 빠른 시작 (5분)

```bash
# 1) 압축 해제 후 폴더로 이동
unzip dart_rag_demo.zip -d dart_rag_demo && cd dart_rag_demo

# 2) 가상환경 + 의존성 설치
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3) API 키 설정
cp .env.example .env               # Windows: copy .env.example .env
#    → .env 파일을 열어 OPENDART_API_KEY, GROQ_API_KEY 값 입력 (아래 3절 참고)

# 4) 삼성전자 2023~2024 보고서 8건 수집·청킹·인덱싱 (약 1~2분, 원문 45MB 다운로드)
python demo.py ingest --corp 삼성전자 --from 20230101 --to 20241231 --skip-amend

# 5) 질문
python demo.py ask "2023년 보통주 1주당 배당금과 연간 배당총액은?"
python demo.py chat                # 대화형 (quit 로 종료)
python run_demo.py                 # 질문 7개 배치 실행 → demo_results.md
```

키가 아직 없어도 파이프라인 확인은 가능합니다: `python demo.py ingest --sample` (합성 샘플, 키 불필요).

---

## 2. 실행 환경

| 항목 | 요구사항 |
|---|---|
| Python | **3.10 이상** (3.12~3.14 에서 테스트) |
| OS | Linux / macOS / Windows 모두 가능 (순수 파이썬, 컴파일 불필요) |
| 메모리 | 2GB 이상 (8건 인덱싱 시 약 1GB 사용) |
| 디스크 | 약 300MB (`data/raw` 원문 캐시 45MB + `data/vectordb` 인덱스 + `wiki/`) |
| 네트워크 | `opendart.fss.or.kr`, `api.groq.com` 접근 |
| GPU | 불필요 |

의존 패키지 (`requirements.txt`): `requests`, `beautifulsoup4`, `lxml`, `numpy`, `rank_bm25`, `openai`(Groq도 이 SDK로 호출), `python-dotenv`

---

## 3. API 키 설정

### 3-1. 필요한 키

| 키 | 필수 | 용도 | 발급 (무료) |
|---|---|---|---|
| `OPENDART_API_KEY` | **필수** | 공시 목록·원문 다운로드 | https://opendart.fss.or.kr → 회원가입 → **인증키 신청/관리** → 즉시 발급 (일 20,000건) |
| `GROQ_API_KEY` | LLM용 (권장) | 답변 생성 (`openai/gpt-oss-120b`) | https://console.groq.com → **API Keys** → Create (무료 티어: 분당 8,000 토큰) |
| `OPENAI_API_KEY` | 선택 (유료) | 있으면 LLM + **임베딩**까지 사용 → 검색 품질 향상 | https://platform.openai.com |

- LLM 키가 하나도 없으면 답변 대신 **관련 발췌 상위 3개**를 그대로 출력합니다(추출식 폴백).
- 우선순위: `GROQ_API_KEY` → `OPENAI_API_KEY` → 없음.
- 임베딩: `OPENAI_API_KEY` 가 있으면 `text-embedding-3-small`, 없으면 **로컬 해싱 임베딩**(외부 호출 없음) + BM25 로 동작.

### 3-2. 넣는 방법 (셋 중 하나)

**방법 A — `.env` 파일 (권장)**
```bash
cp .env.example .env
```
```ini
# .env
OPENDART_API_KEY=여기에_DART_키
GROQ_API_KEY=여기에_Groq_키
```
`demo.py` / `run_demo.py` 실행 시 자동으로 읽습니다.

**방법 B — 환경변수**
```bash
export OPENDART_API_KEY=...   # Windows PowerShell: $env:OPENDART_API_KEY="..."
export GROQ_API_KEY=...
```

**방법 C — 코드에서 직접 전달** (라이브러리로 쓸 때)
```python
from dart_rag.dart_client import DartClient
from dart_rag.rag import DartRAG
cli = DartClient(api_key="...")           # DART
rag = DartRAG(store, wiki, model="qwen/qwen3.8-27b")  # LLM 모델 지정, 키는 환경변수에서
```

### 3-3. 선택 설정
```ini
GROQ_MODEL=openai/gpt-oss-120b     # 대안: qwen/qwen3.8-27b, openai/gpt-oss-20b
LLM_MODEL=gpt-4o-mini              # OpenAI 사용 시
EMBED_MODEL=text-embedding-3-small
```
> Groq 무료 티어는 분당 8,000 토큰 제한이 있어 컨텍스트를 9,000자로 자르고, 413/429 응답 시 자동으로 대기·재시도합니다. 배치(`run_demo.py`)에서 질문 사이에 잠깐 멈추는 것은 이 때문입니다.

---

## 4. 코드 구조

```
dart_rag/
  dart_client.py   OpenDART API (corp_code, 공시목록, 원문 zip→XML, data/raw 캐시)
  parser.py        DART XML → Section 트리 / Table (rowspan·colspan 그리드 전개, 다층 헤더 병합, TE/TU 셀)
  chunker.py       ★ 청킹 로직
  wiki.py          위키 (회사 → 보고서 → 섹션 페이지, 주제별 페이지, index.json 그래프)
  store.py         벡터DB(numpy) + BM25 하이브리드(RRF) + 메타 필터 + 섹션제목 부스트
  rag.py           질의→필터 추론 → 검색 → 섹션 확장/small-to-big → LLM 답변
demo.py            CLI: ingest / ask / chat / toc
run_demo.py        질문 배치 실행 → demo_results.md
sample_data.py     합성 샘플 (API 키 없이 파이프라인 검증)
requirements.txt / .env.example
demo_results.md    실데이터 데모 결과 (참고용)
wiki/              위키 예시 페이지 일부 (ingest 시 전체 재생성)
```

실행 후 생성되는 것 (zip 에는 미포함, `ingest` 가 만듦):
```
data/raw/        공시 원문 XML 캐시 (재실행 시 다운로드 생략)
data/vectordb/   chunks.jsonl + vectors.npy + info.json
wiki/            삼성전자/<보고서>/<섹션>.md, _topics/*.md, index.json
```

---

## 5. 청킹 로직 요약

| 단계 | 내용 |
|---|---|
| breadcrumb | 모든 청크 앞에 `[삼성전자 \| 사업보고서 2023.12 \| III. 재무에 관한 사항 > 6. 배당에 관한 사항]` |
| 텍스트 | 섹션 경계 엄수, 문단 누적 ~900자(최대 1,400), 1문단 overlap, 초장문 800자 강제 분할 |
| 표 | 헤더 반복 + 글자 예산(1,400자) 기반 row-group; 10열 초과 시 첫 열 고정 + 열 그룹 분할; 1열 표(단위·설명)는 텍스트로 |
| 표 KV | 각 행을 `매출액(제55기)=258,935,494 백만원` 형태로 선형화한 별도 청크 (수치 질의용), 단위는 앞 문단 `(단위 : …)` 에서 상속 |
| 메타 | corp, report_type, period, rcept_no, section_path, tags, unit, parent_id(위키 섹션 페이지) |

파라미터는 `DartChunker(target_chars, max_chars, overlap_paras, table_rows_per_chunk, max_cols, table_chars)` 로 조정.

## 6. 검색·답변
- 질문에서 `2023년 사업보고서` / `2024년 3분기` → `{report_type, period}` 필터 자동 추론
- Dense(임베딩) + BM25(한글 bigram·숫자 토큰) RRF 융합, 섹션 제목 토큰 매칭 부스트, 주석 섹션 감점
- 상위 섹션의 표 KV 청크 동반 확장 → 본문만 걸려도 같은 섹션의 수치 표가 컨텍스트에 포함
- 답변은 `[n]` 출처 번호 + 보고서·섹션 경로를 함께 출력

## 7. 다른 회사 / 기간
```bash
python demo.py ingest --corp SK하이닉스 --from 20240101 --to 20241231
python demo.py toc <접수번호>        # 파싱된 목차 확인 (data/raw 에 원문이 있어야 함)
```
`--corp` 는 DART 등록 법인명과 정확히 일치해야 합니다.

## 8. 자주 겪는 문제
| 증상 | 원인 / 해결 |
|---|---|
| `OPENDART_API_KEY 가 필요합니다` | `.env` 위치가 `demo.py` 와 같은 폴더인지, 키 앞뒤 공백·따옴표 확인 |
| `DART list 오류 020` | DART 일일 호출 한도 초과 |
| `model_not_found` (Groq) | Groq 모델 목록이 바뀜 → `GROQ_MODEL` 을 console.groq.com 의 현재 모델로 변경 |
| `rate_limit_exceeded` 413/429 | 무료 티어 TPM 초과, 자동 재시도됨. 잦으면 `DartRAG.max_ctx_chars` 를 줄이거나 `-k 4` |
| 답변이 "확인되지 않습니다" | 검색이 빗나간 경우. 질문에 보고서 종류·연도·섹션 키워드(배당, 최대주주 등)를 넣으면 개선 |
| 임베더 변경 후 결과 이상 | `data/vectordb` 삭제 후 재 `ingest` (임베더가 다르면 기존 인덱스를 자동 무시) |

## 9. 확장 포인트
- 임베딩 교체: `store.py` 의 `Embedder` 클래스(`embed(texts)->ndarray`, `name`, `dim`) 하나만 구현 — bge-m3, Gemini, Upstage 등
- 벡터 스토어 교체: `VectorStore.add/search` 를 Chroma/Qdrant/pgvector 로
- LLM 교체: `rag.py` 의 `DartRAG.__init__` 에서 OpenAI 호환 `base_url` 만 바꾸면 Ollama/vLLM/Together 등 그대로 사용
- 시계열 비교: `wiki/_topics/*.md` 의 크로스 리포트 링크로 다중 보고서 컨텍스트 조립
