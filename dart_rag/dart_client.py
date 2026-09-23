"""OpenDART API 클라이언트.

- corp_code 조회 (corpCode.xml zip)
- 공시 목록 조회 (list.json)  : 사업보고서(A001) / 반기(A002) / 분기(A003)
- 공시 원문 다운로드 (document.xml zip → DART XML 문자열)
"""
from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

BASE = "https://opendart.fss.or.kr/api"
REPORT_TYPES = {"A001": "사업보고서", "A002": "반기보고서", "A003": "분기보고서"}


@dataclass
class Filing:
    rcept_no: str
    corp_code: str
    corp_name: str
    report_nm: str
    rcept_dt: str

    @property
    def report_type(self) -> str:
        if "사업보고서" in self.report_nm:
            return "사업보고서"
        if "반기보고서" in self.report_nm:
            return "반기보고서"
        if "분기보고서" in self.report_nm:
            return "분기보고서"
        return self.report_nm

    @property
    def period(self) -> str:
        """'사업보고서 (2023.12)' → '2023.12'"""
        m = re.search(r"\((\d{4}\.\d{2})\)", self.report_nm)
        return m.group(1) if m else self.rcept_dt[:6]


class DartClient:
    def __init__(self, api_key: str | None = None, cache_dir: str = "data/raw"):
        self.api_key = api_key or os.environ.get("OPENDART_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENDART_API_KEY 가 필요합니다.")
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    # ---------- corp_code ----------
    def corp_code(self, corp_name: str) -> str:
        cache = self.cache / "corpCode.xml"
        if not cache.exists():
            r = requests.get(f"{BASE}/corpCode.xml", params={"crtfc_key": self.api_key}, timeout=60)
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                cache.write_bytes(z.read(z.namelist()[0]))
        xml = cache.read_text("utf-8", errors="ignore")
        # 상장사(stock_code 존재) 우선, 정확 일치
        pat = re.compile(
            r"<list>\s*<corp_code>(\d+)</corp_code>\s*<corp_name>(.*?)</corp_name>\s*"
            r"(?:<corp_eng_name>.*?</corp_eng_name>\s*)?<stock_code>\s*(\S*?)\s*</stock_code>",
            re.S,
        )
        cands = [(c, n, s) for c, n, s in pat.findall(xml) if n.strip() == corp_name]
        if not cands:
            raise ValueError(f"corp_code 를 찾을 수 없음: {corp_name}")
        cands.sort(key=lambda t: (t[2] == "", t[0]))
        return cands[0][0]

    # ---------- 공시 목록 ----------
    def list_filings(self, corp_code: str, bgn_de: str, end_de: str,
                     types: tuple[str, ...] = ("A001", "A002", "A003")) -> list[Filing]:
        out: list[Filing] = []
        for t in types:
            r = requests.get(
                f"{BASE}/list.json",
                params={"crtfc_key": self.api_key, "corp_code": corp_code, "bgn_de": bgn_de,
                        "end_de": end_de, "pblntf_detail_ty": t, "page_count": 100},
                timeout=30,
            )
            j = r.json()
            if j.get("status") != "000":
                if j.get("status") == "013":  # 조회 결과 없음
                    continue
                raise RuntimeError(f"DART list 오류 {j.get('status')}: {j.get('message')}")
            for it in j["list"]:
                # 정정공시([기재정정])도 포함되지만 원본 우선 시 필터 가능
                out.append(Filing(it["rcept_no"], it["corp_code"], it["corp_name"], it["report_nm"], it["rcept_dt"]))
        out.sort(key=lambda f: f.rcept_dt, reverse=True)
        return out

    # ---------- 원문 ----------
    def fetch_document_xml(self, rcept_no: str) -> str:
        cache = self.cache / f"{rcept_no}.xml"
        if cache.exists():
            return cache.read_text("utf-8")
        r = requests.get(f"{BASE}/document.xml", params={"crtfc_key": self.api_key, "rcept_no": rcept_no}, timeout=120)
        r.raise_for_status()
        if not r.content.startswith(b"PK"):
            raise RuntimeError(f"document.xml 응답이 zip 이 아님: {r.text[:200]}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            # 본문 파일: 보통 '{rcept_no}.xml' (첨부는 _숫자 suffix)
            names = sorted(z.namelist(), key=lambda n: (("_" in Path(n).stem), n))
            raw = z.read(names[0])
        text = _decode(raw)
        cache.write_text(text, "utf-8")
        return text


def _decode(raw: bytes) -> str:
    m = re.match(rb'\s*<\?xml[^>]*encoding="([^"]+)"', raw)
    encs = [m.group(1).decode()] if m else []
    for enc in encs + ["utf-8", "euc-kr", "cp949"]:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore")
