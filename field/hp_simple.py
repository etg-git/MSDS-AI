# -*- coding: utf-8 -*-
"""
field/hp_simple.py

섹션 2(유해‧위험성) 텍스트에서
- 유해‧위험문구(H) 전체
- 예방조치문구(P) 전체
를 '라인 그대로' 긁어 모아 보여주는 심플 추출기.

특징
- 섹션 분리는 먼저 sections["hazards"]가 있으면 그걸 우선 사용
- 없으면 가벼운 정규식으로 2→3 구간 슬라이싱
- H/P 코드는 정규식으로 라인 필터, 중복/공백 정리만 수행
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple

# 코드 패턴
H_CODE_RE = re.compile(r"\bH\d{3}[A-Z]?\b")
P_CODE_RE = re.compile(r"\bP\d{3}[A-Z]?(?:\s*\+\s*P\d{3}[A-Z]?)*\b")

# 섹션2 슬라이스(라이트)
RE_SEC2_START = re.compile(
    r"(?:^|\n)\s*(?:2\.|제?\s*2\s*장)?\s*(?:유해\s*[\·\.]?\s*위험\s*성|유해성|위험성|표시\s*사항|Hazard(?:\(s\))?\s*identification|Hazards\s*identification|Label\s*elements)\b",
    re.I
)
RE_NEXT_SECTION = re.compile(
    r"(?:^|\n)\s*(?:3\.|제?\s*3\s*장|구성\s*성분|Composition|Ingredients|Mixture)\b",
    re.I
)

def _slice_sec2(text: str) -> str:
    m = RE_SEC2_START.search(text or "")
    if not m:
        return ""
    m2 = RE_NEXT_SECTION.search(text, m.end())
    end = m2.start() if m2 else len(text)
    return text[m.start():end]

def extract_hp_simple(full_text: str, sections: Dict[str, Dict] | None = None) -> Dict[str, str]:
    """
    반환:
      {
        "hazard_text": "H문구 줄들을 그대로 묶은 텍스트",
        "precaution_text": "P문구 줄들을 그대로 묶은 텍스트",
        "unique_H": "H200, H225, ...",
        "unique_P": "P210, P233+P240, ..."
      }
    """
    # 1) 섹션2 본문 선택
    sec2_text = ""
    if sections:
        # split_sections_auto가 캐논키('hazards')로 저장하는 구조 가정
        sec = sections.get("hazards") or {}
        sec2_text = (sec.get("text") or "").strip()
    if not sec2_text:
        sec2_text = _slice_sec2(full_text or "") or (full_text or "")

    # 2) 라인 단위 필터링
    lines = [re.sub(r"[ \t]+", " ", ln.strip()) for ln in (sec2_text or "").splitlines()]

    hazard_lines: List[str] = []
    precaution_lines: List[str] = []
    uniq_H, uniq_P = [], []

    seen_h_lines, seen_p_lines = set(), set()
    seen_h_codes, seen_p_codes = set(), set()

    for ln in lines:
        if not ln:
            continue

        # H 라인
        if H_CODE_RE.search(ln):
            if ln not in seen_h_lines:
                seen_h_lines.add(ln)
                hazard_lines.append(ln)
            for h in sorted(set(H_CODE_RE.findall(ln))):
                if h not in seen_h_codes:
                    seen_h_codes.add(h)
                    uniq_H.append(h)

        # P 라인
        if P_CODE_RE.search(ln):
            if ln not in seen_p_lines:
                seen_p_lines.add(ln)
                precaution_lines.append(ln)
            # 단일/결합코드 모두 수집(결합코드는 문자열 그대로)
            combo = re.findall(r"\bP\d{3}[A-Z]?(?:\s*\+\s*P\d{3}[A-Z]?)+\b", ln)
            if combo:
                for c in combo:
                    c2 = c.replace(" ", "")
                    if c2 not in seen_p_codes:
                        seen_p_codes.add(c2)
                        uniq_P.append(c2)
            else:
                singles = set(re.findall(r"\bP\d{3}[A-Z]?\b", ln))
                for p in sorted(singles):
                    if p not in seen_p_codes:
                        seen_p_codes.add(p)
                        uniq_P.append(p)

    return {
        "hazard_text": "\n".join(hazard_lines).strip(),
        "precaution_text": "\n".join(precaution_lines).strip(),
        "unique_H": ", ".join(uniq_H),
        "unique_P": ", ".join(uniq_P),
    }
