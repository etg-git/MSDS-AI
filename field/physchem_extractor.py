# -*- coding: utf-8 -*-
"""
물리·화학적 특성(섹션 9) 추출기
- 섹션 9를 제목/패턴으로 찾아 우선 추출, 실패 시 전역 보조 추출
- 라벨 유사어(국/영) 맵핑 + 표/콜론/여러 공백 파싱
- 로그(_log)로 무엇이 왜 매칭되었는지 남김
"""

from __future__ import annotations
import re
from typing import Dict, Any, List, Tuple

# 라벨 유사어 사전 (필요시 확장)
FIELD_ALIASES = {
    "appearance1": [
        "성상",
    ],
    "appearance2": [
        "색상", "색", "color", "colour"
    ],
    "odor": [
        "냄새", "취", "향", "odor", "odour", "smell"
    ],
    "pH": [
        "ph", "pH", "수소이온농도"
    ],
    "melting_point": [
        "융점", "녹는점", "어는점", "빙점", "melting point", "freezing point"
    ],
    "boiling_point": [
        "비점", "끓는점", "boiling point", "initial boiling point"
    ],
    "flash_point": [
        "인화점", "flash point"
    ],
    "evaporation_rate": [
        "증발속도", "evaporation rate"
    ],
    "flammability": [
        "가연성", "인화성", "flammability", "flammable"
    ],
    "explosive_limits": [
        "폭발한계", "폭발범위", "연소한계", "UEL", "LFL", "UFL", "LEL",
        "explosive limits", "flammability limits"
    ],
    "vapor_pressure": [
        "증기압", "증기 압력", "vapour pressure", "vapor pressure"
    ],
    "vapor_density": [
        "증기밀도", "증기 비중", "vapor density", "vapour density"
    ],
    "relative_density": [
        "밀도", "비중", "상대밀도", "relative density", "specific gravity"
    ],
    "solubility": [
        "용해도", "수용해도", "solubility", "water solubility"
    ],
    "partition_coeff": [
        "분배계수", "옥탄올/물 분배계수", "n-옥탄올/물", "partition coefficient", "n-octanol/water"
    ],
    "auto_ignition": [
        "자연발화온도", "자동발화온도", "auto-ignition temperature", "autoignition"
    ],
    "decomposition_temp": [
        "분해온도", "분해 온도", "decomposition temperature"
    ],
    "viscosity": [
        "점도", "viscosity"
    ],
}

# 섹션 9 찾기용 패턴(스플리터 보강과 동일 계열)
SEC9_PATTERNS = [
    r"\b9\)?\s*[\.\)]?\s*물리\s*[·\.]?\s*화학적\s*특성\b",
    r"\bphysical\s*(and|&|\/)?\s*chemical\s*propert(ies|y)\b",
]

# 라벨:값 라인 파싱(콜론/여러 공백/탭)
LABEL_VALUE_PAT = re.compile(r"^\s*(?P<label>[^:：\t]{2,50})\s*[:：\t]\s*(?P<value>.+)$")
TABLIKE_SPLIT  = re.compile(r"\s{2,}|\t+")

def _normalize(s: str) -> str:
    s = s or ""
    s = s.replace("ㆍ", "·").replace("：", ":")
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def _split_lines(s: str) -> List[str]:
    return [ln.rstrip() for ln in s.splitlines()]

def _best_sec9_block(text: str, sections: Dict[str, Dict[str, Any]]) -> Tuple[str, str]:
    """섹션 딕셔너리에서 9번으로 보이는 블록을 우선 반환, 없으면 전역에서 '섹션9 제목~다음 섹션' 범위를 힌트로 자름"""
    # 1) sections에서 찾기
    for k, sec in sections.items():
        title = _normalize(sec.get("title") or k)
        for pat in SEC9_PATTERNS:
            if re.search(pat, title, flags=re.I):
                return sec.get("text", "") or "", f"sections[{k}]"
    # 2) 전역 텍스트에서 구간 추출
    lines = _split_lines(text)
    start, end = -1, len(lines)
    for i, ln in enumerate(lines):
        if any(re.search(p, _normalize(ln), re.I) for p in SEC9_PATTERNS):
            start = i
            break
    if start >= 0:
        for j in range(start + 1, len(lines)):
            if re.match(r"^\s*(1[0-6]|10|11|12|13|14|15|16)\s*[\.\)]", lines[j]):  # 다음 번호 섹션 시작 추정
                end = j
                break
        return "\n".join(lines[start:end]), "global-slice"
    return "", "none"

def _label_hit(label: str, aliases: List[str]) -> bool:
    lab = _normalize(label).lower()
    for a in aliases:
        if _normalize(a).lower() in lab:
            return True
    return False

def _parse_block(block: str) -> Dict[str, str]:
    """
    블록을 라인 단위로 훑으면서 ‘라벨:값’ 또는 다중공백 분리 구조를 파싱.
    """
    result: Dict[str, str] = {}
    lines = _split_lines(block)
    for ln in lines:
        ln_n = _normalize(ln)
        if not ln_n:
            continue
        m = LABEL_VALUE_PAT.match(ln_n)
        if m:
            label = m.group("label").strip()
            value = m.group("value").strip()
        else:
            # 표 구조: “라벨  값” (두 칸 이상 공백)
            parts = TABLIKE_SPLIT.split(ln_n)
            if len(parts) >= 2:
                label = parts[0].strip()
                value = " ".join(parts[1:]).strip()
            else:
                continue
        # 어느 필드로 매핑?
        for field, aliases in FIELD_ALIASES.items():
            if _label_hit(label, aliases):
                # 첫 매칭 우선, 기존 값 있으면 길이가 더 긴 쪽 채택
                prev = result.get(field, "")
                if len(value) > len(prev):
                    result[field] = value
                break
    return result

def extract_physchem(text: str, sections: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    반환: { field: value, ..., "_log": [진행로그] }
    """
    log: List[str] = []
    block, src = _best_sec9_block(text, sections)
    log.append(f"[sec9] source={src}, length={len(block)}")

    out = {}
    if block:
        res = _parse_block(block)
        out.update(res)
        log.append(f"[sec9] parsed_keys={list(res.keys())}")

    # 보조: 섹션 9가 비어있거나 일부만 잡힌 경우, 전역에서 라벨별 한 번 더 보정
    if not out or len(out) < 4:
        lines = _split_lines(text)
        boost = _parse_block("\n".join(lines[: min(2000, len(lines))]))  # 문서 앞쪽에서 한 번 더
        for k, v in boost.items():
            out.setdefault(k, v)
        log.append(f"[fallback] added_keys={list(boost.keys())}")

    out["_log"] = log
    return out
