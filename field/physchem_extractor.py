# -*- coding: utf-8 -*-
"""
physchem_extractor.py
섹션 9(물리·화학적 특성) 추출기 (정규식 1차 → 퍼지 보강 2차 → 값 파싱)
- KO/EN 동시 대응: 다양한 라벨 동의어(FIELD_ALIASES)로 매칭
- 라벨 줄 다음/다다음 줄까지 값 스캔(표/개행형 레이아웃 보완)
- 범위(~, -, ∼), 부등호(<, >), 단위(℃, mmHg, ㎎/ℓ, mPa·s, g/cm3 등) 파싱
- 결측 표기(해당없음/자료없음/-/—/N/A)는 raw로 보관
- appearance1(성상)/appearance2(색상) 분리, odor(냄새), odor_threshold(냄새역치) 지원
- RapidFuzz가 설치되어 있으면 2차 퍼지 보강 수행(미설치 시 자동 skip)
- 반환: (result_dict, log_list)
"""

from __future__ import annotations
import re
import unicodedata
from typing import Dict, List, Tuple, Any, Optional

# RapidFuzz(선택)
try:
    from rapidfuzz import process, fuzz
    _HAS_RAPID = True
except Exception:
    _HAS_RAPID = False

# ---------------------------------------------------------------------------
# 0) 라벨 동의어 사전 (필요시 자유롭게 보강)
#    키: 표준 필드명 / 값: 문서에서 등장 가능한 라벨 후보(한·영 혼용)
# ---------------------------------------------------------------------------
FIELD_ALIASES: Dict[str, List[str]] = {
    "appearance1": [
        "성상", "상태", "외관", "appearance", "physical state", "state", "form",
    ],
    "appearance2": [
        "색상", "색", "color", "colour",
    ],
    "odor": [
        "냄새", "취", "odor", "odour", "smell",
    ],
    # 신규: 냄새 역치
    "odor_threshold": [
        "냄새 역치", "냄새역치", "odor threshold", "odour threshold",
    ],
    "pH": [
        "pH", "p H", "수소이온농도", "피에이치",
    ],
    "melting_point": [
        "녹는점", "융점", "어는점", "빙점", "melting point", "freezing point",
    ],
    "boiling_point": [
        "끓는점", "비점", "boiling point",
        # 복합 표기 케이스 보강
        "초기 끓는점", "initial boiling point",
    ],
    # 신규: 끓는 범위 (보일링 레인지)
    "boiling_range": [
        "끓는 범위", "boiling range", "끓는점 범위", "초기 끓는 점/끓는 범위",
    ],
    "flash_point": [
        "인화점", "flash point",
    ],
    "evaporation_rate": [
        "증발 속도", "증발속도", "evaporation rate",
    ],
    "flammability": [
        "인화성", "가연성", "flammability", "flammable", "combustibility",
        # (고체, 기체) 라벨이 같이 오는 경우도 이 키로 먼저 흡수
        "인화성 (고체, 기체)", "flammability (solid, gas)"
    ],
    # 하/상한을 따로 받는 필드 추가
    "explosive_lower": [
        "폭발한계(하한)", "가연한계(하한)", "inflammability or explosion limit (lower)",
        "lower explosive limit", "LEL", "하한",
    ],
    "explosive_upper": [
        "폭발한계(상한)", "가연한계(상한)", "inflammability or explosion limit (upper)",
        "upper explosive limit", "UEL", "상한",
    ],
    # 기존 통합 키는 유지(문서가 한 줄에 같이 주는 경우)
    "explosive_limits": [
        "폭발한계", "가연한계", "explosive limits", "inflammability or explosion range",
    ],
    "vapor_pressure": [
        "증기압", "vapor pressure", "vapour pressure",
    ],
    "vapor_density": [
        "증기 밀도", "증기밀도", "vapor density", "vapour density",
    ],
    # 신규: density(절대밀도) 추가
    "density": [
        "밀도", "density", "bulk density", "kg/l", "g/ml", "g/cm3",
    ],
    "relative_density": [
        "상대 밀도", "비중", "relative density", "specific gravity",
        "density (relative)", "Ref Std:WATER=1",
    ],
    "solubility": [
        "용해도", "용해성", "solubility", "soluble",
    ],
    # 신규: 물 이외 용해도
    "solubility_non_water": [
        "용해도-non-water", "비수용해도", "solubility (non-water)", "solubility in organic",
    ],
    "partition_coeff": [
        "분배계수", "n-옥탄올/물 분배계수", "octanol/water", "partition coefficient",
        "Pow", "log Pow", "log Kow", "Kow",
    ],
    "autoignition_temp": [
        "자연발화 온도", "자연발화온도", "auto-ignition temperature", "autoignition temperature",
    ],
    "decomposition_temp": [
        "분해 온도", "분해온도", "decomposition temperature",
    ],
    "viscosity": [
        "점도", "viscosity", "kinematic viscosity", "dynamic viscosity",
        "mPa·s", "mPa-s", "cP",
    ],
    # 신규: 분자량
    "molecular_weight": [
        "분자량", "molecular weight", "molar mass",
    ],
    # VOC 계열
    "voc_content": [
        "VOC", "휘발성 유기물", "휘발성 유기화합물", "VOC content",
        "VOC 함량", "VOC content (calculated)",
    ],
    # 신규: 퍼센트 휘발성
    "percent_volatile": [
        "퍼센트 휘발성", "percent volatile", "% volatile",
    ],
    # 신규: VOC Less H2O & Exempt Solvents
    "voc_less_h2o_exempt": [
        "VOC Less H2O & Exempt Solvents", "VOC less H2O and exempt solvents",
        "SCAQMD rule 443.1",
    ],
}

# ---------------------------------------------------------------------------
# 1) 결측/무응답 표기 화이트리스트
# ---------------------------------------------------------------------------
MISSING_TOKENS = {"해당없음", "자료없음", "-", "—", "N/A", "n/a", "not applicable", "none", "no data", "not available"}

def _is_missing_token(s: str) -> bool:
    return s.strip().lower() in MISSING_TOKENS

# ---------------------------------------------------------------------------
# 2) 텍스트 정규화 & 라인 분리
# ---------------------------------------------------------------------------
def _normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\u00A0", " ", s)      # NBSP → space
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\r\n?", "\n", s)
    return s.strip()

def _split_lines(s: str) -> List[str]:
    return [ln.strip() for ln in s.split("\n")]

# ---------------------------------------------------------------------------
# 3) 값 파싱(범위/부등호/단위)
#    - 예: "5.0~8.0", "< 0.1", "2.16 g/cm3", "9.01 mmHg (at 100℃)" 등
# ---------------------------------------------------------------------------
VALUE_TOKEN = r"[<>]?\s*-?\d{1,3}(?:,\d{3})*(?:\.\d+)?"
RANGE_TOKEN = rf"{VALUE_TOKEN}(?:\s*[\-~∼~]\s*{VALUE_TOKEN})?"
UNIT_TOKEN  = r"(?:℃|°C|K|°F|Pa|kPa|MPa|bar|mbar|mmHg|atm|mg/L|g/L|g/ml|g/mL|g/cm3|kg/m3|kg/L|kg/l|cP|mPa·s|mPa-s|%|ppm|ppb|—|-)?"
VALUE_RE    = rf"({RANGE_TOKEN})\s*({UNIT_TOKEN})?"

def _parse_value(raw: str) -> Dict[str, Any]:
    """
    숫자/범위/부등호/단위를 구조화. '자료 없음/해당없음/없음' 등은 raw만 유지.
    천단위 콤마 제거, 단위는 캐치한 그대로 보관.
    """
    raw = (raw or "").strip().strip(";,.")
    # 비가용 표현 처리
    if re.search(r"(자료\s*없음|해당\s*없음|없음|N/?A|not applicable)", raw, re.I):
        return {"raw": raw}

    m = re.search(VALUE_RE, raw, flags=re.IGNORECASE)
    if not m:
        return {"raw": raw}

    value_token = m.group(1)
    unit_token  = (m.group(2) or "").strip()

    # 부등호 추출
    cmp_op = None
    if value_token.lstrip().startswith("<"):
        cmp_op = "<"
        value_token = value_token.lstrip()[1:].strip()
    elif value_token.lstrip().startswith(">"):
        cmp_op = ">"
        value_token = value_token.lstrip()[1:].strip()

    # 콤마 제거
    value_token_clean = value_token.replace(",", "")

    out: Dict[str, Any] = {"raw": raw}
    if cmp_op:
        out["cmp"] = cmp_op

    # 범위 or 단일
    if re.search(r"[\-~∼~]", value_token_clean):
        parts = re.split(r"[\-~∼~]", value_token_clean)
        try:
            low  = float(parts[0].strip())
            high = float(parts[1].strip())
        except Exception:
            low, high = value_token_clean, None
        out["low"] = low
        if high is not None:
            out["high"] = high
    else:
        try:
            out["value"] = float(value_token_clean.strip())
        except Exception:
            out["value"] = value_token_clean.strip()

    if unit_token:
        out["unit"] = unit_token
    return out

# ---------------------------------------------------------------------------
# 4) 라벨:값 추출 정규식 & 윈도우 스캔
# ---------------------------------------------------------------------------
def _label_value_regex(label: str) -> re.Pattern:
    """
    - "라벨 : 값" / "라벨 - 값" / "라벨  값" 등 완화된 패턴
    - 라벨이 줄 머리/중간 어디 있어도 매칭(단어경계)
    """
    return re.compile(
        rf"(?P<label>\b{re.escape(label)}\b)\s*(?:[:：\-–—]|\s)\s*(?P<value>.+)",
        flags=re.IGNORECASE
    )

def _value_after_colon_or_table(line: str) -> str:
    """
    - 같은 줄에서 콜론 뒤 값
    - 없으면 공백 2칸 이상 분리 테이블의 마지막 컬럼
    """
    m = re.search(r"[:：]\s*(.+)$", line)
    if m:
        return m.group(1).strip()
    parts = re.split(r"\s{2,}", line)
    if len(parts) >= 2:
        return parts[-1].strip()
    return ""

def _value_from_likely_label_line(label_line: str, lines: List[str], idx: Optional[int]) -> Dict[str, Any]:
    """
    라벨 줄에서 값 추정: 같은 줄 → 다음 줄 → 다다음 줄
    """
    # a) 같은 줄
    same = _value_after_colon_or_table(label_line)
    if same:
        return _parse_value(same)

    # b) 다음 줄
    if idx is not None and idx + 1 < len(lines):
        nxt = lines[idx + 1].strip()
        if nxt:
            return _parse_value(nxt)

    # c) 다다음 줄
    if idx is not None and idx + 2 < len(lines):
        nn = lines[idx + 2].strip()
        if nn:
            return _parse_value(nn)

    return {}

# ---------------------------------------------------------------------------
# 5) 1차 패스: 정규식 기반 매칭
#     - 각 필드의 모든 alias를 컴파일해서 라인별 탐색
#     - 매칭되면 값 파싱 → result[field] = parsed
# ---------------------------------------------------------------------------
def _regex_pass(lines: List[str]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    found: Dict[str, Any] = {}
    matched_labels: List[str] = []
    log: List[str] = []

    compiled: Dict[str, List[re.Pattern]] = {
        field: [_label_value_regex(lbl) for lbl in aliases]
        for field, aliases in FIELD_ALIASES.items()
    }

    for ln in lines:
        if not ln:
            continue
        for field, patterns in compiled.items():
            for pat in patterns:
                m = pat.search(ln)
                if not m:
                    continue
                raw_val = (m.group("value") or "").strip()
                if not raw_val and ":" in ln:
                    raw_val = _value_after_colon_or_table(ln) or ""
                parsed = _parse_value(raw_val) if raw_val else {"raw": ""}
                found[field] = parsed
                matched_labels.append(m.group("label"))
                log.append(f"[regex] {field} <- '{m.group('label')}' | raw='{raw_val}'")
                break  # 같은 필드에서 다중 alias 충돌 방지
    return found, matched_labels, log

# ---------------------------------------------------------------------------
# 6) 1차 보강: appearance/odor 블록 후속 스캔
#    - 어떤 문서에서는 "외관" 헤더 아래 다음 줄들에 "성상/색상/냄새..."가 몰려 있음
# ---------------------------------------------------------------------------
def _appearance_block_followup(lines: List[str], result: Dict[str, Any], log: List[str]) -> None:
    # 외관/appearance가 라벨로만 있고 값이 없을 때, 바로 아래 3~4줄을 스캔
    target_heads = {"외관", "appearance"}
    heads_idx = []
    for i, ln in enumerate(lines):
        token = ln.lower().replace(":", " ").strip()
        if token in target_heads:
            heads_idx.append(i)

    for idx in heads_idx:
        for j in range(1, 5):  # 다음 4줄 탐색
            k = idx + j
            if k >= len(lines):
                break
            ln = lines[k]
            # 성상/색상/냄새/냄새역치 라벨이 포함되면 값으로 처리
            for key, aliases in [("appearance1", FIELD_ALIASES["appearance1"]),
                                ("appearance2", FIELD_ALIASES["appearance2"]),
                                ("odor", FIELD_ALIASES["odor"]),
                                ("odor_threshold", FIELD_ALIASES["odor_threshold"])]:
                if result.get(key):
                    continue
                for lb in aliases:
                    if re.search(rf"\b{re.escape(lb)}\b", ln, flags=re.IGNORECASE):
                        # 같은 줄 값 우선 → 없으면 다음/다다음 줄
                        parsed = _value_from_likely_label_line(ln, lines, k)
                        if parsed:
                            result[key] = parsed
                            log.append(f"[block] {key} from follow-up around 'appearance' | line={k+1}")
                            break

# ---------------------------------------------------------------------------
# 7) 2차 패스: 퍼지(Fuzzy) 보강 (정규식에서 못 찾은 필드만 채움)
#    - RapidFuzz 설치 시 사용, 미설치면 skip
# ---------------------------------------------------------------------------
def _fuzzy_pass(lines: List[str], result: Dict[str, Any], matched_labels: List[str], score_cutoff: int = 92) -> Tuple[Dict[str, Any], List[str]]:
    logs: List[str] = []
    if not _HAS_RAPID:
        logs.append("[fuzzy] rapidfuzz not available → skip")
        return {}, logs

    # 라벨 후보 풀
    label_pool = [ln for ln in lines if ln and ln.strip()]
    if not label_pool:
        logs.append("[fuzzy] empty label pool → skip")
        return {}, logs

    # 이미 채워진 필드는 제외하고, 그 필드의 alias 중 하나를 질의로 삼아 근접 라벨 라인을 찾는다
    missing_fields = [f for f in FIELD_ALIASES.keys() if f not in result]
    out: Dict[str, Any] = {}

    for field in missing_fields:
        aliases = FIELD_ALIASES[field]
        # 각 필드별 alias들 중 하나를 대표로 fuzz 검색 (여러 개 시도)
        best_choice, best_score, best_idx = None, -1, None
        best_alias = None

        for guess in aliases:
            # rapidfuzz 버전에 따라 extractOne 반환 튜플 길이가 다를 수 있음
            best = process.extractOne(guess, label_pool, scorer=fuzz.WRatio, score_cutoff=score_cutoff)
            if not best:
                continue
            choice = best[0]
            score  = best[1]
            idx    = None
            if len(best) > 2:
                idx = best[2]

            if score > best_score:
                best_choice, best_score, best_idx = choice, score, idx
                best_alias = guess

        if best_choice:
            # best_choice가 있는 라인 인덱스 재탐색(안전)
            if best_idx is None:
                try:
                    best_idx = lines.index(best_choice)
                except ValueError:
                    best_idx = None

            parsed = _value_from_likely_label_line(best_choice, lines, best_idx)
            if parsed:
                out[field] = parsed
                logs.append(f"[fuzzy] {field} ← '{best_alias}' ~ '{best_choice}' score={best_score} value='{parsed.get('raw','')}'")
            else:
                logs.append(f"[fuzzy] {field} matched '{best_choice}' but no value")
        else:
            logs.append(f"[fuzzy] {field} no candidate over cutoff={score_cutoff}")

    return out, logs

# ---------------------------------------------------------------------------
# 8) 엔트리 포인트
#    - 입력: 섹션 9 텍스트(한 덩어리 문자열)
#    - 출력: (result_dict, logs)
# ---------------------------------------------------------------------------
def extract_physchem(sec9_text: str) -> Tuple[Dict[str, Any], List[str]]:
    logs: List[str] = []
    text = _normalize_text(sec9_text or "")
    if not text:
        return {}, ["[physchem] empty section 9 text"]

    lines = _split_lines(text)

    # 1차: 정규식 매칭
    result, matched_labels, log1 = _regex_pass(lines)
    logs.extend(log1)

    # 1차 보강: appearance/odor 등의 블록 후속 스캔
    _appearance_block_followup(lines, result, logs)

    # 2차: 퍼지 보강 (정규식으로 못 채운 필드만)
    add, log2 = _fuzzy_pass(lines, result, matched_labels, score_cutoff=92)
    result.update(add)
    logs.extend(log2)

    # 결과 요약 로그
    parsed_keys = sorted([k for k in result.keys() if k != "_log"])
    logs.append(f"[physchem] parsed_keys={parsed_keys}")

    # result에 로그 포함시키진 않고(상위 매퍼에서 별도 로그 관리하는 경우),
    # 필요하다면 아래 주석을 해제하여 함께 반환해도 됨.
    # result["_log"] = logs

    return result, logs
