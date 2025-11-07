# utils/robust_pdf_text.py
# Visual-order 텍스트 추출: words + rawdict 폴백, 2~3단 감지, 헤더/푸터 제거, 하이픈 교정

from __future__ import annotations
import re
from typing import List, Tuple, Optional

try:
    import fitz  # PyMuPDF
except Exception as e:
    raise RuntimeError("PyMuPDF(fitz)가 필요합니다. pip install pymupdf") from e

RE_HYPHEN_JOIN = re.compile(r"([A-Za-z])-\n([A-Za-z])")
RE_MULTI_BLANK = re.compile(r"[ \t]+")
RE_MULTI_NL = re.compile(r"\n{3,}")

def _median(vals: List[float], default=10.0) -> float:
    if not vals:
        return default
    s = sorted(vals)
    return s[len(s)//2]

def _strip_headers_footers(page_text: str) -> str:
    # 페이지 머리말/바닥글로 흔한 토큰 제거 후보: 페이지 번호, 문서코드/Rev 등
    lines = [ln for ln in page_text.splitlines()]
    if len(lines) <= 6:
        return page_text
    # 상하 각 2줄에서 반복되는 패턴 제거(간단)
    head = lines[:2]
    foot = lines[-2:]
    bad_tokens = []
    for z in head + foot:
        if re.search(r"^\s*page\s*\d+|^\s*\d+\s*/\s*\d+|revision|rev\.?\s*\d", z, re.I):
            bad_tokens.append(z.strip())
    if bad_tokens:
        lines = [ln for ln in lines if ln.strip() not in bad_tokens]
    return "\n".join(lines)

def _detect_columns(words: List[Tuple]) -> List[List[Tuple]]:
    if not words:
        return [words]
    xs = sorted(set(int(w[0]) for w in words))
    heights = [w[3]-w[1] for w in words]
    h_med = _median(heights, 10.0)
    gaps = []
    for i in range(len(xs)-1):
        gaps.append((xs[i+1]-xs[i], xs[i], xs[i+1]))
    big = [g for g in gaps if g[0] > h_med * 6]
    if not big:
        return [words]
    big.sort(reverse=True)
    cut_points = []
    for g in big[:2]:  # 최대 3단까지
        _, xL, xR = g
        cut_points.append((xL+xR)/2.0)
    cut_points.sort()
    cols = [[] for _ in range(len(cut_points)+1)]
    for w in words:
        x0 = w[0]
        idx = 0
        while idx < len(cut_points) and x0 > cut_points[idx]:
            idx += 1
        cols[idx].append(w)
    return [c for c in cols if c] or [words]

def _extract_by_words(page) -> str:
    words = page.get_text("words")  # (x0,y0,x1,y1,word,block,line,word_no)
    if not words:
        return ""
    heights = [w[3]-w[1] for w in words]
    h_med = _median(heights, 10.0)
    y_tol = max(3.0, h_med * 0.6)
    gap_thr = h_med * 0.3

    lines_out: List[str] = []
    for col in _detect_columns(words):
        col.sort(key=lambda w: (round(w[1]/y_tol), w[0]))
        current = None
        buf: List[Tuple[float,float,float,float,str]] = []
        def flush():
            if not buf:
                return
            buf.sort(key=lambda t: t[0])
            out = []
            prev_x1 = None
            for x0,y0,x1,y1,tk in buf:
                if prev_x1 is not None and (x0 - prev_x1) > gap_thr:
                    out.append(" ")
                out.append(tk)
                prev_x1 = x1
            lines_out.append("".join(out))
        for w in col:
            ykey = round(w[1]/y_tol)
            if current is None:
                current = ykey
            if ykey != current:
                flush(); buf = []
                current = ykey
            buf.append((w[0], w[1], w[2], w[3], w[4]))
        flush()
        lines_out.append("")  # 컬럼 간 빈 줄
    text = "\n".join(lines_out)
    return text

def _extract_by_rawdict(page) -> str:
    d = page.get_text("rawdict")
    blocks = [b for b in d.get("blocks", []) if b.get("type", 0) == 0]
    blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    out = []
    for b in blocks:
        for ln in b.get("lines", []):
            spans = ln.get("spans", [])
            spans.sort(key=lambda s: s["bbox"][0])
            out.append("".join(s.get("text","") for s in spans))
        out.append("")
    return "\n".join(out)

def _cleanup(text: str) -> str:
    if not text:
        return ""
    text = RE_HYPHEN_JOIN.sub(r"\1\2", text)
    text = RE_MULTI_BLANK.sub(" ", text)
    text = RE_MULTI_NL.sub("\n\n", text)
    return text.strip()

def extract_pdf_text_visual_order(
    pdf_path: str,
    max_pages: Optional[int] = None,
    prefer: str = "words",  # words | rawdict | auto
) -> str:
    doc = fitz.open(pdf_path)
    parts = []
    n = min(len(doc), max_pages) if max_pages else len(doc)
    for i in range(n):
        page = doc[i]
        if prefer in ("words", "auto"):
            body = _extract_by_words(page)
            if not body and prefer == "auto":
                body = _extract_by_rawdict(page)
        else:
            body = _extract_by_rawdict(page)
        body = _strip_headers_footers(body)
        parts.append(_cleanup(body))
    return "\n\n".join(parts).strip()
