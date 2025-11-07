# -*- coding: utf-8 -*-
"""
SHMS 매핑(요약)
- 섹션 힌트 기반으로 기본정보/연락처/보관·취급/노출기준 후보를 라벨 매칭(정규식→퍼지)
- GHS(신호어/H/P/분류)는 기존 ghs_extractor 사용
- 섹션 9(물리·화학적 특성)는 physchem_extractor로 세분 항목 추출
- 구성성분/CAS/법규 키워드도 동시 수집
- 상세 로그를 _log로 반환
"""

from __future__ import annotations
import re
from typing import Dict, Any, List, Tuple
from rapidfuzz import process, fuzz

from field.physchem_extractor import extract_physchem

# (필요시) 너의 GHS 추출기 모듈
try:
    from field.ghs_extractor import extract_ghs_all
except Exception:
    def extract_ghs_all(text, sections):
        return {"signal_word": None, "hazard_statements": [], "precautionary_statements": [], "classification": [], "_log": ["[ghs] dummy"]}

CAS_RE = r"\b(\d{2,7}-\d{2}-\d)\b"
H_RE   = r"\bH\d{3}[A-Z]?\b"
P_RE   = r"\bP\d{3}[A-Z]?(?:\+P\d{3}[A-Z]?)?\b"

SCORE_MIN = 72
WINDOW_AFTER = 3
MAX_VALUE_LEN = 260

SECTION_HINTS = {
    "1":  ["식별", "제품", "표지", "identifier", "identification"],
    "2":  ["유해", "위험", "hazard", "ghs"],
    "3":  ["구성", "성분", "원료", "composition", "ingredient", "mixture"],
    "7":  ["취급", "저장", "handling", "storage"],
    "8":  ["노출", "개인보호", "exposure", "personal protection", "PPE"],
    "9":  ["물리", "화학", "특성", "physical", "chemical", "properties"],
    "11": ["독성", "toxicological"],
    "15": ["규제", "법규", "regulatory"],
    "16": ["기타", "참고", "other", "misc", "reference"],
}

LABELS = {
    "product_name": ["제품명", "물질명", "제품 식별자", "표지명", "상표명", "Product name", "Substance name", "Product identifier", "Trade name"],
    "supplier": ["제조사", "제조업체", "공급사", "수입사", "제조자", "회사명", "Manufacturer", "Supplier", "Producer", "Importer", "Company name"],
    "emergency_phone": ["긴급전화", "비상 전화", "응급전화", "야간 비상연락처", "Emergency phone", "Emergency telephone", "Emergency contact"],
    "phone": ["전화", "연락처", "Tel", "Phone", "Contact", "Customer service"],
    "intended_use": ["권장 용도", "용도", "금지용도", "Recommended use", "Intended use", "Restriction on use"],
    "storage": ["보관", "저장", "Storage", "Store", "Storing"],
    "handling": ["취급", "Handling", "Handling and storage"],
    "exposure_limit": ["노출기준", "직업적 노출한계", "TWA", "STEL", "PEL", "Occupational exposure limits", "Exposure limits"],
    "legal_keywords": ["화관법", "화평법", "산안법", "관계법령", "K-REACH", "REACH", "GHS"],
}

PHONE_RE = r"(?:\+?\d{1,3}[-\s]?)?(?:\d{2,4}[-\s]?)?\d{3,4}[-\s]?\d{4}"

def _split_lines(text: str) -> List[str]:
    return [ln.rstrip() for ln in text.splitlines()]

def _value_after_colon_or_table(line: str) -> str:
    m = re.search(r"[:：]\s*(.+)$", line)
    if m: return m.group(1).strip()
    parts = re.split(r"\s{2,}", line)
    if len(parts) >= 2: return parts[-1].strip()
    return line.strip()

def _truncate(s: str, n: int = MAX_VALUE_LEN) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + " …"

def _fuzzy_best(lines: List[str], labels: List[str]) -> List[Tuple[int, int]]:
    lower_map = {i: ln.lower() for i, ln in enumerate(lines)}
    q = " / ".join(labels).lower()
    res = process.extract(q, lower_map, scorer=fuzz.partial_ratio, limit=10)
    out: List[Tuple[int, int]] = []
    for choice, score, idx in res:
        if score >= SCORE_MIN:
            out.append((idx, score))
    out = sorted(set(out), key=lambda x: (-x[1], x[0]))[:2]
    return out

def _window(lines: List[str], center: int, after: int = WINDOW_AFTER) -> str:
    a = max(0, center)
    b = min(len(lines), center + after + 1)
    return "\n".join(lines[a:b])

def _pick_from_sections_then_global(text: str, sections: Dict[str, Dict], labels: List[str],
                                    extra_regex: List[re.Pattern] | None = None) -> Tuple[str, str, List[str]]:
    logs: List[str] = []
    lines_all = _split_lines(text)

    # 섹션 후보 선택(제목/키에서 번호 추정)
    def hint(title: str, sec_no: str) -> bool:
        title = (title or "").lower()
        for kw in SECTION_HINTS.get(sec_no, []):
            if kw.lower() in title:
                return True
        return False

    cand = []
    for k, sec in sections.items():
        title = (sec.get("title") or k or "").strip()
        m = re.search(r"(\d{1,2})", k + " " + title)
        sec_no = m.group(1) if m else ""
        if not sec_no: continue
        if hint(title, sec_no):
            cand.append((k, sec_no, title))

    # 블록 스캐너
    def scan(block: str, where: str) -> Tuple[str, str]:
        # (a) 라벨:값
        for lb in labels:
            m = re.search(rf"{re.escape(lb)}\s*[:：]\s*(.+)", block, re.I)
            if m:
                return _truncate(m.group(1)), f"{where}:regex({lb})"
        # (b) 퍼지 → 윈도우 → 값
        bl = _split_lines(block)
        for idx, sc in _fuzzy_best(bl, labels):
            win = _window(bl, idx)
            for lb in labels:
                m = re.search(rf"{re.escape(lb)}\s*[:：]\s*(.+)", win, re.I)
                if m:
                    return _truncate(m.group(1)), f"{where}:fuzzy+regex({lb},{sc})"
            nxt = idx + 1 if idx + 1 < len(bl) else idx
            val = _value_after_colon_or_table(bl[idx]) if idx == nxt else bl[nxt].strip()
            if val and (val.lower() not in ("n/a", "not applicable")):
                return _truncate(val), f"{where}:fuzzy+nextline({sc})"
        # (c) 추가 정규식(전화 등)
        if extra_regex:
            for rx in extra_regex:
                m = rx.search(block)
                if m: return _truncate(m.group(0)), f"{where}:extra_regex"
        return "", ""

    for k, sec_no, title in cand:
        block = sections[k].get("text", "") or ""
        if not block.strip(): continue
        v, src = scan(block, f"section[{k}:{title}]")
        logs.append(f"[section-scan] {k}:{title} -> {bool(v)} via {src or 'none'}")
        if v: return v, src, logs

    v, src = scan(text, "global")
    logs.append(f"[global-scan] -> {bool(v)} via {src or 'none'}")
    return v, src, logs

def _extract_composition(text: str) -> List[Dict[str, Any]]:
    rows = []
    for ln in _split_lines(text):
        m = re.search(CAS_RE, ln)
        if not m: continue
        cas = m.group(1)
        conc_m = re.search(r"(\d{1,3}(?:\.\d+)?\s*%|\d+\s*ppm|\d+\s*mg/m\^?3)", ln, re.I)
        name = ln[:m.start()].strip(" -:\t")
        rows.append({"name": re.sub(r"\s{2,}", " ", name), "cas": cas, "concentration": conc_m.group(1) if conc_m else ""})
    # CAS 기준 중복 제거
    out, seen = [], set()
    for r in rows:
        if r["cas"] in seen: continue
        seen.add(r["cas"]); out.append(r)
    return out

def _extract_legal_regulations(text: str) -> List[Dict[str, Any]]:
    out = []
    for kw in LABELS["legal_keywords"]:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.I):
            out.append({"keyword": kw, "found": True})
    return out

def _get_section9_text(sections: Dict[str, Dict[str, Any]], full_text: str) -> Tuple[str, str]:
    """
    섹션 사전에서 9번 본문을 우선 가져오고, 없으면 full_text에서 라이트하게 추정.
    반환: (sec9_text, source_note)
    """
    # 키 변형 대응
    for k in ("9", "sec9", "section9"):
        if k in sections and sections[k].get("text", "").strip():
            return sections[k]["text"], f"sections[{k}]"
    # 타이틀에 9가 들어간 섹션 탐색
    for k, sec in sections.items():
        title = (sec.get("title") or "").strip()
        if re.search(r"\b9\b", k) or re.search(r"\b9\b", title):
            t = sec.get("text", "")
            if t.strip():
                return t, f"sections[{k}:{title}]"
    # fallback: 전역에서 “9.”로 시작하는 블록 추정(아주 완화)
    m = re.search(r"\n\s*9\.\s*.*?(?=\n\s*\d+\.\s*|$)", full_text, flags=re.S)
    if m:
        return m.group(0), "global-slice"
    return "", "none"
  
  
def map_to_shms(text: str, sections: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    debug: List[str] = []

    product_name, src1, d1 = _pick_from_sections_then_global(text, sections, LABELS["product_name"])
    debug += [f"[product_name] {x}" for x in d1] + [f"[product_name] src={src1} val={product_name!r}"]

    supplier, src2, d2 = _pick_from_sections_then_global(text, sections, LABELS["supplier"])
    debug += [f"[supplier] {x}" for x in d2] + [f"[supplier] src={src2} val={supplier!r}"]

    intended_use, src3, d3 = _pick_from_sections_then_global(text, sections, LABELS["intended_use"])
    debug += [f"[intended_use] {x}" for x in d3] + [f"[intended_use] src={src3} val={intended_use!r}"]

    emer_val, src4, d4 = _pick_from_sections_then_global(text, sections, LABELS["emergency_phone"], extra_regex=[re.compile(PHONE_RE)])
    debug += [f"[emergency_phone] {x}" for x in d4] + [f"[emergency_phone] src={src4} val={emer_val!r}"]

    phone_val, src5, d5 = _pick_from_sections_then_global(text, sections, LABELS["phone"], extra_regex=[re.compile(PHONE_RE)])
    if phone_val == emer_val: phone_val = ""  # 충돌 방지
    debug += [f"[phone] {x}" for x in d5] + [f"[phone] src={src5} val={phone_val!r}"]

    storage, src6, d6 = _pick_from_sections_then_global(text, sections, LABELS["storage"])
    debug += [f"[storage] {x}" for x in d6] + [f"[storage] src={src6} val={storage!r}"]

    handling, src7, d7 = _pick_from_sections_then_global(text, sections, LABELS["handling"])
    debug += [f"[handling] {x}" for x in d7] + [f"[handling] src={src7} val={handling!r}"]

    exposure_note, src8, d8 = _pick_from_sections_then_global(text, sections, LABELS["exposure_limit"])
    debug += [f"[exposure] {x}" for x in d8] + [f"[exposure] src={src8} val={exposure_note!r}"]

    composition = _extract_composition(text)
    legal_regs  = _extract_legal_regulations(text)
    debug.append(f"[composition] rows={len(composition)}")
    debug.append(f"[legal] hits={len(legal_regs)}")

    # GHS
    ghs = extract_ghs_all(text, sections)
    debug += [f"[ghs] {m}" for m in ghs.get("_log", [])]

    # 섹션 9 본문만 우선 사용 (없으면 전역 텍스트로 폴백)
    sec9_text = (
      sections.get("9", {}).get("text", "")
      or sections.get("sec9", {}).get("text", "")
      or sections.get("section9", {}).get("text", "")
    )

    if sec9_text.strip():
        # extract_physchem는 (result_dict, log_list) 반환
        physchem_result, physchem_log = extract_physchem(sec9_text)
        debug += [f"[physchem] {m}" for m in physchem_log]
    else:
        # 섹션9가 비어있으면 전역 텍스트로 한 번 시도
        physchem_result, physchem_log = extract_physchem(text)
        debug += ["[physchem] sec9 empty → fallback to global text"] + [f"[physchem] {m}" for m in physchem_log]

    # 최종 리턴에 담을 때 로그 키는 제외
    result_physchem = {k: v for k, v in physchem_result.items() if k != "_log"}

    # 전역 패턴 통계
    H_all   = sorted(set(re.findall(H_RE, text)))
    P_all   = sorted(set(re.findall(P_RE, text)))
    CAS_all = sorted(set(re.findall(CAS_RE, text)))
    debug.append(f"[pattern] H={len(H_all)} P={len(P_all)} CAS={len(CAS_all)}")

    return {
        "basic": {
            "product_name": product_name,
            "supplier":     supplier,
        },
        "site_usage": {
            "intended_use": intended_use,
        },
        "contacts": {
            "emergency_phone": emer_val,
            "phone":           phone_val,
        },
        "storage": {
            "storage":  storage,
            "handling": handling,
        },
        "exposure": {
            "note": exposure_note,
        },
        "composition": composition,
        "legal_regulations": legal_regs,
        "ghs_detail": {
            "signal_word": ghs.get("signal_word"),
            "hazard_statements": ghs.get("hazard_statements", []),
            "precautionary_statements": ghs.get("precautionary_statements", []),
            "classification": ghs.get("classification", []),
        },
        # 여기!
        "physchem": result_physchem,
        "_log": debug,
    }
