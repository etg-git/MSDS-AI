# -*- coding: utf-8 -*-
"""
GHS 핵심 필드 추출:
- 신호어 (Signal word)
- 유해·위험문구 (Hazard statements, Hxxx + 문장)
- 예방조치문구 (Precautionary statements, Pxxx + 문장)
- 분류 (GHS Classification: 예) Flammable liquids, Category 2 / 인화성 액체(2급))

입력:
    text: 전체 문서 문자열
    sections: split_sections_auto() 결과 dict (가능하면 '2' 또는 'hazard_identification' 등 key가 포함됨)
출력:
    dict {
        "signal_word": "위험|경고|Danger|Warning|None",
        "hazard_statements": [{"code":"H225","text":"고도로 인화성 액체 및 증기"}, ...],
        "precautionary_statements": [{"code":"P210","text":"열·스파크·화염으로부터 멀리…"}, ...],
        "classification": [{"category":"Flammable liquids","level":"2"}, ...],
        "_log": [추출 근거/경로 로그]
    }
"""

import re
from typing import Dict, List, Tuple, Optional
from rapidfuzz import process, fuzz

# 코드 + 문장 라인 캡처용
H_LINE_RE = re.compile(r"\b(H\d{3}[A-Z]?)\b[:\s\-–]*([^\n]+)")
P_LINE_RE = re.compile(r"\b(P\d{3}[A-Z]?(?:\+P\d{3}[A-Z]?)*)\b[:\s\-–]*([^\n]+)")

# 신호어 후보
SIGNAL_WORDS = [
    "위험", "경고", "Danger", "Warning"
]

# 분류 캡처 (영문/국문 혼합 대응)
# 예시: Flammable liquids, Category 2
#      인화성 액체 (제2류) / 인화성 액체 2급 / Category 2
CLASS_LINE_RE = re.compile(
    r"(?:(Category|카테고리)\s*(\d{1,2}))|"
    r"(?:(\b[1-5]\b)\s*(급|류))|"
    r"(?:\(\s*제?\s*([1-5])\s*류\s*\))",
    flags=re.I
)

# 섹션 2(유해성·위험성) 유사 키워드
SEC2_KEYS = [
    "2", "hazard identification", "hazard identification (ghs)",
    "위험성", "유해성", "유해·위험성", "GHS 분류", "표지요소", "표지 기재사항"
]

def _pick_section_text(sections: Dict[str, Dict], prefer_keys: List[str], fallback_text: str) -> Tuple[str, List[str]]:
    """섹션 dict에서 우선순위 키 후보를 RapidFuzz로 찾아 해당 섹션 본문을 주고, 없으면 전문 fallback."""
    logs = []
    if not sections:
        logs.append("ghs: no sections → use full text")
        return fallback_text, logs

    titles = {k: (v.get("title","") + " " + v.get("text","")[:200]).lower() for k,v in sections.items()}
    joined_keys = "/".join(prefer_keys).lower()
    matches = process.extract(joined_keys, titles, scorer=fuzz.partial_ratio, limit=3)

    # result item: (choice(str), score, key)
    for item in matches:
        choice, score, key = item[0], item[1], item[2]
        if score >= 70 and key in sections:
            logs.append(f"ghs: use section[{key}] score={score}")
            return sections[key].get("text",""), logs

    logs.append("ghs: no close section → use full text")
    return fallback_text, logs

def extract_signal_word(text: str, sections: Dict[str, Dict]) -> Tuple[Optional[str], List[str]]:
    src, logs = _pick_section_text(sections, SEC2_KEYS, text)
    # 신호어 후보를 우선순위 매칭
    for w in SIGNAL_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", src, flags=re.I):
            logs.append(f"signal_word: {w}")
            return w, logs
    logs.append("signal_word: not found")
    return None, logs

def extract_hazard_statements(text: str, sections: Dict[str, Dict]) -> Tuple[List[Dict], List[str]]:
    src, logs = _pick_section_text(sections, SEC2_KEYS, text)
    items = []
    seen = set()
    for m in H_LINE_RE.finditer(src):
        code = m.group(1).strip()
        sent = m.group(2).strip().rstrip(" ;,ㆍ·")
        key = (code, sent)
        if key in seen: 
            continue
        seen.add(key)
        items.append({"code": code, "text": sent})
    logs.append(f"hazard_statements: {len(items)} found")
    return items, logs

def extract_precautionary_statements(text: str, sections: Dict[str, Dict]) -> Tuple[List[Dict], List[str]]:
    src, logs = _pick_section_text(sections, SEC2_KEYS, text)
    items = []
    seen = set()
    for m in P_LINE_RE.finditer(src):
        code = m.group(1).strip()
        sent = m.group(2).strip().rstrip(" ;,ㆍ·")
        key = (code, sent)
        if key in seen:
            continue
        seen.add(key)
        items.append({"code": code, "text": sent})
    logs.append(f"precautionary_statements: {len(items)} found")
    return items, logs

def extract_classification(text: str, sections: Dict[str, Dict]) -> Tuple[List[Dict], List[str]]:
    """
    GHS 분류 행을 느슨하게 캐치:
      - 라벨 예: 'Flammable liquids, Category 2', '인화성 액체 2급', '유기 과산화물 (제2류)'
      - 출력: [{"category": "Flammable liquids / 인화성 액체", "level": "2"}]
    """
    src, logs = _pick_section_text(sections, SEC2_KEYS, text)
    lines = [ln.strip() for ln in src.splitlines() if ln.strip()]
    out, seen = [], set()

    # 카테고리명 후보(앞단 텍스트)를 일부 보존: 콤마/괄호 기준 분절
    for ln in lines:
        if not re.search(r"(Category|카테고리|[1-5]\s*(급|류)|제\s*[1-5]\s*류)", ln, flags=re.I):
            continue
        # 카테고리 이름 추정
        head = re.split(r"[，,;]", ln)[0]
        head = re.sub(r"\s*\(.*?\)\s*", " ", head)  # 괄호 내용 제거(가끔 중복)
        head = re.sub(r"\s{2,}", " ", head).strip()
        # 등급 추출
        m = CLASS_LINE_RE.search(ln)
        level = None
        if m:
            # 우선순위로 잡히는 그룹에서 숫자 뽑기
            for g in (2, 3, 5):
                if m.group(g):
                    level = m.group(g)
                    break
        key = (head, level or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({"category": head, "level": level or ""})

    logs.append(f"classification: {len(out)} found")
    return out, logs

def extract_ghs_all(text: str, sections: Dict[str, Dict]) -> Dict:
    out = {"signal_word": None, "hazard_statements": [], "precautionary_statements": [], "classification": [], "_log": []}
    sw, lg1 = extract_signal_word(text, sections)
    hz, lg2 = extract_hazard_statements(text, sections)
    pr, lg3 = extract_precautionary_statements(text, sections)
    cl, lg4 = extract_classification(text, sections)
    out["signal_word"] = sw
    out["hazard_statements"] = hz
    out["precautionary_statements"] = pr
    out["classification"] = cl
    out["_log"].extend(lg1 + lg2 + lg3 + lg4)
    return out
