# field/composition_extractor.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple

try:
    from rapidfuzz import process, fuzz
    _HAS_RAPID = True
except Exception:
    _HAS_RAPID = False

CAS_RE = r"\b(\d{2,7}-\d{2}-\d)\b"

# 농도 토큰: %, ppm, mg/m3, g/L, 범위, 부등호 포함
VAL = r"[<>]?\s*\d{1,3}(?:[.,]\d+)?"
RANGE = rf"{VAL}\s*(?:[-~–~]\s*{VAL})?"
UNIT = r"(?:%|ppm|ppb|mg\/m\^?3|mg\/m3|mg\/L|g\/L|g\/ml|g\/mL|g\/cm3|wt\.?%|vol\.?%)"
CONC_RE = rf"({RANGE})\s*(?:{UNIT})?"
CONC_UNIT_RE = rf"({RANGE})\s*({UNIT})"

# 헤더 후보(다국어/변형)
HEADER_ALIASES = {
    "name": ["성분명", "성분", "물질명", "Name", "Substance", "Ingredient", "Component"],
    "cas":  ["CAS", "CAS No", "CAS-No", "CAS 번호", "CAS번호", "CAS Number", "CAS Registry No"],
    "conc": ["함량", "농도", "비율", "含量", "Content", "Concentration", "wt%", "%", "Range"],
    "ec":   ["EC", "EINECS", "EC No", "EC번호", "등록번호", "Registration No", "REACH Reg No"],
    "etc":  ["비고", "주석", "Note", "Remarks"],
}

_SPLITERS = [
    r"\s*\|\s*",         # 파이프 테이블
    r"\t+",              # 탭
    r"\s{2,}",           # 공백 간격
    r"\s*;\s*",          # 세미콜론
]

def _best_header_map(head_line: str) -> Tuple[Dict[str,int], List[str]]:
    """헤더 라인에서 열→표준키 매핑. RapidFuzz 있으면 퍼지, 없으면 포함 매칭."""
    cols = _split_cols(head_line)
    keys = list(HEADER_ALIASES.keys())
    col2key: Dict[int,str] = {}
    used = set()
    logs = []

    def score(term: str, label: str) -> int:
        if _HAS_RAPID:
            return fuzz.WRatio(term.lower(), label.lower())
        return 100 if label.lower() in term.lower() else 0

    for i, c in enumerate(cols):
        best_key, best_s = None, -1
        for k, aliases in HEADER_ALIASES.items():
            for lab in aliases:
                s = score(c, lab)
                if s > best_s:
                    best_key, best_s = k, s
        if best_key and best_s >= (70 if _HAS_RAPID else 1) and best_key not in used:
            col2key[i] = best_key
            used.add(best_key)
            logs.append(f"[header] '{c}' -> {best_key} ({best_s})")
        else:
            logs.append(f"[header] '{c}' -> (no map, score={best_s})")

    return col2key, logs

def _split_cols(line: str) -> List[str]:
    s = line.strip().strip("|").strip()
    for sp in _SPLITERS:
        parts = re.split(sp, s)
        if len(parts) >= 2:
            return [p.strip() for p in parts]
    # 콤마 분리(열이 2~4개일 때만 시도)
    parts = [p.strip() for p in re.split(r"\s*,\s*", s)]
    return parts

def _parse_conc(s: str) -> Dict[str, Any]:
    if not s: return {"raw": ""}
    raw = s.strip()
    out: Dict[str, Any] = {"raw": raw}
    m2 = re.search(CONC_UNIT_RE, raw, flags=re.I)
    m1 = re.search(CONC_RE, raw, flags=re.I)
    m = m2 or m1
    if not m:
        return out
    val = m.group(1)
    unit = (m.group(2) if m2 else "")
    # 부등호
    cmp_op = None
    val2 = val.strip()
    if val2.startswith("<"): cmp_op, val2 = "<", val2[1:].strip()
    if val2.startswith(">"): cmp_op, val2 = ">", val2[1:].strip()
    # 범위
    if re.search(r"[-~–~]", val2):
        a, b = re.split(r"[-~–~]", val2, maxsplit=1)
        out["low"] = _to_float(a)
        out["high"] = _to_float(b)
    else:
        out["value"] = _to_float(val2)
    if cmp_op: out["cmp"] = cmp_op
    if unit: out["unit"] = unit
    return out

def _to_float(x: str):
    try:
        return float(x.replace(",", ".").strip())
    except Exception:
        return x.strip()

def extract_composition(text: str, comp_section_text: str | None = None) -> Tuple[List[Dict[str,str]], List[str], List[str]]:
    """
    반환: (rows, missed_lines, logs)
      rows: [{name, cas, concentration_raw, conc_value/low/high/cmp/unit, ec_no, note}]
    """
    logs: List[str] = []
    src = comp_section_text.strip() if comp_section_text and comp_section_text.strip() else text
    lines = [ln.rstrip() for ln in src.splitlines() if ln.strip()]
    if not lines:
        return [], [], ["[comp] empty text"]

    # 1) 헤더 라인 찾기(최초 20줄에서 best 후보)
    header_idx, header_map, header_logs = None, {}, []
    for i in range(min(20, len(lines))):
        cols = _split_cols(lines[i])
        if len(cols) >= 2:
            hm, lg = _best_header_map(lines[i])
            if hm and ("name" in hm or "cas" in hm or "conc" in hm):
                header_idx, header_map, header_logs = i, hm, lg
                break
    logs += header_logs
    start = (header_idx + 1) if header_idx is not None else 0

    rows: List[Dict[str,str]] = []
    missed: List[str] = []

    # 2) 행 스캔 + 줄 이어붙이기
    carry_name = ""
    for i in range(start, len(lines)):
        ln = lines[i]
        cols = _split_cols(ln)

        # (A) 표형(열 2개 이상): header_map 있으면 매핑, 없으면 휴리스틱
        if len(cols) >= 2:
            data = {"name":"", "cas":"", "concentration_raw":"", "ec_no":"", "note":""}
            # 매핑 적용
            if header_map:
                for ci, val in enumerate(cols):
                    key = header_map.get(ci)
                    if not key:
                        continue
                    if key == "name": data["name"] = val
                    elif key == "cas": data["cas"] = val
                    elif key == "conc": data["concentration_raw"] = val
                    elif key == "ec": data["ec_no"] = val
                    elif key == "etc": data["note"] = val
            else:
                # 휴리스틱: CAS가 포함된 칸 찾기, 농도 단위 포함 칸 찾기
                cas_idx = next((k for k,v in enumerate(cols) if re.search(CAS_RE, v)), -1)
                conc_idx = next((k for k,v in enumerate(cols) if re.search(CONC_RE, v, re.I)), -1)
                if cas_idx >= 0:
                    data["cas"] = re.search(CAS_RE, cols[cas_idx]).group(1)
                    # 이름은 CAS 왼쪽/가장 긴 칸
                    left = cols[:cas_idx] or [""]
                    data["name"] = max(left, key=len).strip()
                if conc_idx >= 0:
                    data["concentration_raw"] = cols[conc_idx].strip()
                # EC 번호
                ec_m = re.search(r"\b(?:EC|EINECS|등록번호)\b[:：]?\s*([A-Za-z0-9\-\.]+)", ln, re.I)
                if ec_m: data["ec_no"] = ec_m.group(1)
