# -*- coding: utf-8 -*-
"""
SHMS 매핑 (섹션 우선 / 정규식 우선 / 퍼지 보강 / 충돌해결 / 디버그 로그)
- 섹션 우선 탐색: 1,2,3,7,8,9,11,15,16 섹션에서 먼저 후보 탐색
- 라벨 다음 줄/표 구조까지 한 번 더 훑음(윈도우 스니펫)
- 긴급전화 vs 일반전화 충돌 분리
- 퍼지 스코어 임계값/타이브레이커 강화
- GHS/PhysChem 통합 (기존 ghs_extractor/physchem_extractor 사용)
"""

from __future__ import annotations
import re
from typing import Dict, List, Tuple, Any
from rapidfuzz import process, fuzz

from field.ghs_extractor import extract_ghs_all
from field.physchem_extractor import extract_physchem

CAS_RE = r"\b(\d{2,7}-\d{2}-\d)\b"
H_RE   = r"\bH\d{3}[A-Z]?\b"
P_RE   = r"\bP\d{3}[A-Z]?(?:\+P\d{3}[A-Z]?)?\b"

# ---- 튜닝 파라미터 ----
SCORE_MIN     = 72      # 퍼지 매칭 최소 점수
WINDOW_BEFORE = 0       # 라벨 줄 앞쪽 라인 포함 개수
WINDOW_AFTER  = 3       # 라벨 줄 뒤쪽(값이 나오는) 라인 포함 개수
TAKE_FIRST_N  = 2       # 섹션/전역 각각 상위 N개만 후보로
MAX_VALUE_LEN = 260     # 값 잘림 방지용 최대 길이

# 섹션 키워드 힌트(문서의 title을 기반으로 대략 매핑)
SECTION_HINTS = {
    "1":  ["식별", "제품", "표지", "identifier", "identification"],
    "2":  ["유해", "위험", "hazard", "ghs"],
    "3":  ["구성", "성분", "원료", "composition", "ingredient", "mixture"],
    "7":  ["취급", "저장", "handling", "storage"],
    "8":  ["노출", "개인보호구", "exposure", "personal protection", "PPE"],
    "9":  ["물리", "화학", "특성", "physical", "chemical", "properties"],
    "11": ["독성", "toxicological"],
    "15": ["규제", "법규", "regulatory"],
    "16": ["기타", "참고", "other", "misc", "reference"],
}

# SHMS 대상 라벨(한글/영문 포함, 상황 따라 더 추가 가능)
LABELS = {
    "product_name": [
        "제품명", "물질명", "제품 식별자", "표지명", "상표명",
        "Product name", "Substance name", "Product identifier", "Trade name"
    ],
    "supplier": [
        "제조사", "제조업체", "공급사", "수입사", "제조자", "회사명"
        "Manufacturer", "Supplier", "Producer", "Importer", "Company name"
    ],
    "emergency_phone": [
        "긴급전화", "비상 전화", "응급전화", "야간 비상연락처",
        "Emergency phone", "Emergency telephone", "Emergency contact"
    ],
    "phone": [
        "전화", "연락처", "Tel", "Phone", "Contact", "Customer service"
    ],
    "intended_use": [
        "권장 용도", "용도", "금지용도",
        "Recommended use", "Intended use", "Restriction on use"
    ],
    "storage": [
        "보관", "저장", "Storage", "Store", "Storing"
    ],
    "handling": [
        "취급", "Handling", "Handling and storage"
    ],
    "exposure_limit": [
        "노출기준", "직업적 노출한계", "TWA", "STEL", "PEL",
        "Occupational exposure limits", "Exposure limits"
    ],
    "legal_keywords": [
        "화관법", "화평법", "산안법", "관계법령", "K-REACH", "REACH", "GHS"
    ],
}

PHONE_RE = r"(?:\+?\d{1,3}[-\s]?)?(?:\d{2,4}[-\s]?)?\d{3,4}[-\s]?\d{4}"

# ---------------- 공통 유틸 ----------------

def _split_lines(text: str) -> List[str]:
    return [ln.rstrip() for ln in text.splitlines()]

def _value_after_colon_or_table(line: str) -> str:
    # 라벨: 값  혹은  공백 2칸 이상으로 분리된 마지막 컬럼 사용
    m = re.search(r"[:：]\s*(.+)$", line)
    if m:
        return m.group(1).strip()
    parts = re.split(r"\s{2,}", line)
    if len(parts) >= 2:
        return parts[-1].strip()
    return line.strip()

def _truncate(s: str, n: int = MAX_VALUE_LEN) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + " …"

def _fuzzy_best(lines: List[str], labels: List[str]) -> List[Tuple[int, int]]:
    """
    퍼지매칭으로 라인번호/스코어 후보 반환 (상위 TAKE_FIRST_N개)
    반환: [(idx, score), ...]
    """
    lower_map = {i: ln.lower() for i, ln in enumerate(lines)}
    q = " / ".join(labels).lower()
    res = process.extract(q, lower_map, scorer=fuzz.partial_ratio, limit=10)
    out: List[Tuple[int, int]] = []
    for choice, score, idx in res:
        if score >= SCORE_MIN:
            out.append((idx, score))
    # 인접 중복 줄 제거 + 상위 N개
    out = sorted(set(out), key=lambda x: (-x[1], x[0]))[:TAKE_FIRST_N]
    return out

def _window(lines: List[str], center: int,
            before: int = WINDOW_BEFORE, after: int = WINDOW_AFTER) -> str:
    a = max(0, center - before)
    b = min(len(lines), center + after + 1)
    return "\n".join(lines[a:b])


def _dedup_rows_by_key(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    seen, out = set(), []
    for r in rows:
        k = r.get(key, "")
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out

# ---------------- 조합 탐색(섹션 → 전역) ----------------

def _pick_from_sections_then_global(
    text: str,
    sections: Dict[str, Dict],
    labels: List[str],
    extra_regex: List[re.Pattern] | None = None
) -> Tuple[str, str, str, List[str]]:
    """
    1) 섹션 제목 힌트(SECTION_HINTS)에 맞는 섹션 본문에서 먼저 탐색(정규식→퍼지→윈도우)
    2) 실패하면 문서 전역에서 탐색
    반환: (value, source_note, debug_label, debug_logs)
    """
    debug: List[str] = []
    lines_all = _split_lines(text)

    # 1) 섹션 후보 모으기
    def is_hint_match(title: str, sec_no: str) -> bool:
        title = (title or "").lower()
        for kw in SECTION_HINTS.get(sec_no, []):
            if kw.lower() in title:
                return True
        return False

    candidate_sections = []
    for k, sec in sections.items():
        title = (sec.get("title") or k or "").strip()
        # 섹션번호 추정 (키가 "2", "sec2" 등일 수도 있어 숫자만 추출)
        m = re.search(r"(\d{1,2})", k + " " + title)
        sec_no = m.group(1) if m else ""
        if not sec_no:
            continue
        if is_hint_match(title, sec_no):
            candidate_sections.append((k, sec_no, title))

    # 섹션 내 탐색 함수
    def scan_block(block: str, where: str) -> Tuple[str, str]:
        # (a) 강한 정규식: "라벨 : 값" 라인 우선
        for lb in labels:
            pat = re.compile(rf"{re.escape(lb)}\s*[:：]\s*(.+)", re.I)
            m = pat.search(block)
            if m:
                val = _truncate(m.group(1))
                return val, f"{where}:regex({lb})"
        # (b) 퍼지: 라벨 근처 윈도우에서 값 추정
        bl = _split_lines(block)
        cands = _fuzzy_best(bl, labels)
        for idx, sc in cands:
            win = _window(bl, idx)
            # 윈도우 내에서 다시 정규식으로 값 뽑기
            for lb in labels:
                pat = re.compile(rf"{re.escape(lb)}\s*[:：]\s*(.+)", re.I)
                m = pat.search(win)
                if m:
                    return _truncate(m.group(1)), f"{where}:fuzzy+regex({lb},{sc})"
            # 마지막: 라벨 줄 다음 줄을 값으로 가정(표 형태 대비)
            nxt = (idx + 1) if idx + 1 < len(bl) else idx
            val = _value_after_colon_or_table(bl[idx]) if idx == nxt else bl[nxt].strip()
            if val and (val.lower() not in ("n/a", "not applicable")):
                return _truncate(val), f"{where}:fuzzy+nextline(score={sc})"
        # (c) 추가 정규식(전화 등)
        if extra_regex:
            for rx in extra_regex:
                m = rx.search(block)
                if m:
                    return _truncate(m.group(0)), f"{where}:extra_regex"
        return "", ""

    # 섹션에서 먼저
    for k, sec_no, title in candidate_sections:
        block = sections[k].get("text", "") or ""
        if not block.strip():
            continue
        val, src = scan_block(block, f"section[{k}:{title}]")
        debug.append(f"[section-scan] {k}:{title} -> {bool(val)} via {src or 'none'}")
        if val:
            return val, src, f"{labels[:2]}", debug

    # 실패 시 전역
    val, src = scan_block(text, "global")
    debug.append(f"[global-scan] -> {bool(val)} via {src or 'none'}")
    return val, src, f"{labels[:2]}", debug

# ---------------- 구성성분/법규/기본패턴 ----------------

def _extract_composition(text: str) -> List[Dict[str, Any]]:
    rows = []
    for ln in _split_lines(text):
        m_cas = re.search(CAS_RE, ln)
        if not m_cas:
            continue
        cas = m_cas.group(1)
        # %/ppm/mg/m3 등 함량 후보
        conc_m = re.search(r"(\d{1,3}(?:\.\d+)?\s*%|\d+\s*ppm|\d+\s*mg/m\^?3)", ln, re.I)
        # 성분명은 CAS 앞부분을 이름으로 가정(간단 버전)
        left = ln[:m_cas.start()].strip(" -:\t")
        name = re.sub(r"\s{2,}", " ", left)
        rows.append({"name": name, "cas": cas, "concentration": conc_m.group(1) if conc_m else ""})
    return _dedup_rows_by_key(rows, "cas")

def _extract_legal_regulations(text: str) -> List[Dict[str, Any]]:
    out = []
    for kw in LABELS["legal_keywords"]:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.I):
            out.append({"keyword": kw, "found": True})
    return out

# ---------------- 메인: SHMS 매핑 ----------------

def map_to_shms(text: str, sections: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    debug: List[str] = []

    # 기본정보/연락처/용도/보관·취급: 섹션→전역 순으로 라벨 탐색
    product_name, src1, _, d1 = _pick_from_sections_then_global(text, sections, LABELS["product_name"])
    debug += [f"[product_name] {s}" for s in d1] + [f"[product_name] src={src1} val={product_name!r}"]

    supplier, src2, _, d2 = _pick_from_sections_then_global(text, sections, LABELS["supplier"])
    debug += [f"[supplier] {s}" for s in d2] + [f"[supplier] src={src2} val={supplier!r}"]

    intended_use, src3, _, d3 = _pick_from_sections_then_global(text, sections, LABELS["intended_use"])
    debug += [f"[intended_use] {s}" for s in d3] + [f"[intended_use] src={src3} val={intended_use!r}"]

    # 연락처: 긴급전화는 emergency 단어 포함 여부/라벨 우선, 일반전화는 나머지
    emer_val, src4, _, d4 = _pick_from_sections_then_global(
        text, sections, LABELS["emergency_phone"], extra_regex=[re.compile(PHONE_RE)]
    )
    debug += [f"[emergency_phone] {s}" for s in d4] + [f"[emergency_phone] src={src4} val={emer_val!r}"]

    phone_val, src5, _, d5 = _pick_from_sections_then_global(
        text, sections, LABELS["phone"], extra_regex=[re.compile(PHONE_RE)]
    )
    # 긴급전화 문자열과 동일하면 일반전화는 비움(중복 방지)
    if phone_val == emer_val:
        phone_val = ""
    debug += [f"[phone] {s}" for s in d5] + [f"[phone] src={src5} val={phone_val!r}"]

    storage, src6, _, d6 = _pick_from_sections_then_global(text, sections, LABELS["storage"])
    debug += [f"[storage] {s}" for s in d6] + [f"[storage] src={src6} val={storage!r}"]

    handling, src7, _, d7 = _pick_from_sections_then_global(text, sections, LABELS["handling"])
    debug += [f"[handling] {s}" for s in d7] + [f"[handling] src={src7} val={handling!r}"]

    exposure_note, src8, _, d8 = _pick_from_sections_then_global(text, sections, LABELS["exposure_limit"])
    debug += [f"[exposure] {s}" for s in d8] + [f"[exposure] src={src8} val={exposure_note!r}"]

    # 구성성분/법규
    composition = _extract_composition(text)
    legal_regs  = _extract_legal_regulations(text)
    debug.append(f"[composition] rows={len(composition)}")
    debug.append(f"[legal] hits={len(legal_regs)}")

    # GHS/PhysChem
    ghs = extract_ghs_all(text, sections)
    phys = extract_physchem(text, sections)
    debug += [f"[ghs] {m}" for m in ghs.get("_log", [])]
    debug += [f"[physchem] {m}" for m in phys.get("_log", [])]

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
        "physchem": {k: v for k, v in phys.items() if k != "_log"},
        "_log": debug,
    }
