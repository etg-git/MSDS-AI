# field/legal_reg_table.py
# 목적: 섹션 15(법적 규제사항) 범위에서 "규제사항(규제항목 코드/명)"만 정규화해 표로 반환
# 출력 컬럼:
#   section(항상 "15"), item_code, item_name_raw, item_name, status, cas_ref, source, match_score
# 요구:
#   1) 법규/관할(scope, law) 제거 — 규제항목만
#   2) 정규식 + rapidfuzz 병행 매칭 (rapidfuzz 미설치 시 정규식/사전 기반으로 폴백)

from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple, Optional

# ---------- 섹션 15 슬라이서 ----------
RE_SEC15 = re.compile(
    r"(?:^|\n)\s*(?:1?5\.|제?\s*15\s*장)\s*(?:법?\s*적?\s*규\s*제\s*(?:현황|사항)?|규제\s*정보|Regulatory\s*information)\b",
    re.I,
)
RE_NEXT = re.compile(
    r"(?:^|\n)\s*(?:1?6\.|제?\s*16\s*장|기타|그\s*밖의\s*참고|Other\s*information)\b",
    re.I,
)

def _slice_sec15(full_text: str) -> str:
    if not full_text:
        return ""
    m = RE_SEC15.search(full_text)
    if not m:
        return ""
    start = m.start()
    m2 = RE_NEXT.search(full_text, m.end())
    end = m2.start() if m2 else len(full_text)
    return full_text[start:end]


# ---------- 기본 패턴 ----------
# 규제항목 코드: D######## 또는 확장형 D12010003.001
CODE_RX = r"D\d{7}(?:\.\d+)?"
RE_CODE = re.compile(CODE_RX)

# "코드 → 이름" 동일 행에서 추출
RE_CODE_NAME = re.compile(rf"({CODE_RX})\s*[:\-]?\s*([^\n\r]+)")
# "이름 → 코드" 동일 행에서 추출
RE_NAME_CODE = re.compile(rf"([^\n\r]+?)\s*[:\-]?\s*({CODE_RX})")

# 상태/부수정보
STATUS_PAT = re.compile(
    r"(해당\s*없음|비\s*해당|자료\s*없음|해당\s*됨|해당|not\s*applicable|n/?a|none|not\s*listed|listed)",
    re.I,
)
CAS_RE = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")

def _norm_status(s: Optional[str]) -> str:
    if not s:
        return ""
    v = s.lower()
    if any(k in v for k in ("해당없", "비해당", "자료없", "not applicable", "n/a", "none", "not listed")):
        return "비해당/자료없음"
    if "listed" in v:
        return "등재/리스트"
    if "해당" in v:
        return "해당"
    return ""

# 이름 후처리
TAIL_NOISE = re.compile(r"\s{2,}.*$")     # 과다 공백 뒤 꼬리 내림
TRAIL_PUNC = re.compile(r"[·\-\|,:;]+$")  # 말미 구두점 정리

def _clean_name(name: str) -> str:
    s = name.strip()
    s = TAIL_NOISE.sub("", s)
    s = TRAIL_PUNC.sub("", s)
    # 슬래시·괄호로 붙는 설명 과감히 절단(빈도 높은 꼬리)
    s = re.split(r"[/（）\(\)]", s)[0].strip()
    return s


# ---------- 규제항목 표준 어휘(정규화 대상) ----------
# 코드 없이 이름만 들어온 경우 또는 이름 변형을 표준화하기 위한 레퍼런스.
# 필요 시 자유롭게 추가/수정.
CANON_ITEMS: List[str] = [
    # 화관/화평/산안/위험물/환경계열 대표 항목
    "기초화학물질", "유독물질", "허가물질", "제한물질", "금지물질",
    "사고대비물질", "배출량조사대상화학물질", "PRTR1그룹", "PRTR2그룹",
    "등록대상기초화학물질", "중점관리물질", "CMR등록물질",
    "제조금지물질", "제조허가대상물질", "노출기준설정대상물질", "작업자노출기준",
    "관리대상유해물질", "특수건강검진대상유해인자", "특별관리물질",
    "허용기준 설정 대상 유해인자", "공정안전관리대상물질", "국소배기장치 안전검사 대상물질",
    "특수고압가스", "가연성가스", "특정고압가스", "독성가스",
    "제1류", "제2류", "제3류", "제4류", "제5류", "제6류", "지정수량", "위험물",
    "대기오염물질", "특정대기유해물질", "휘발성유기화합물", "기후생태계변화유발물질",
    "온실가스", "유해대기오염물질",
    "수질오염물질", "특정수질유해물질",
    "토양오염물질",
    "특정물질",  # 오존층
    "폐유기용제", "지정폐기물",
]

# 동의어/흔한 변형(우선 정규식 치환 → 이후 fuzzy)
SYNONYM_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"배출량\s*조사.*(화학\s*물질)?|PRTR\s*대상", re.I), "배출량조사대상화학물질"),
    (re.compile(r"중점\s*관리\s*물질", re.I), "중점관리물질"),
    (re.compile(r"CMR.*등록.*물질", re.I), "CMR등록물질"),
    (re.compile(r"작업\s*자?\s*노출\s*기준", re.I), "작업자노출기준"),
    (re.compile(r"특수\s*건강\s*검진.*유해\s*인자", re.I), "특수건강검진대상유해인자"),
    (re.compile(r"공정\s*안전\s*관리.*대상\s*물질", re.I), "공정안전관리대상물질"),
    (re.compile(r"국소\s*배기\s*장치.*안전\s*검사.*대상", re.I), "국소배기장치 안전검사 대상물질"),
    (re.compile(r"휘발\s*성\s*유기\s*화합\s*물", re.I), "휘발성유기화합물"),
    (re.compile(r"유해\s*대기\s*오염\s*물질", re.I), "유해대기오염물질"),
    (re.compile(r"특정\s*대기\s*유해\s*물질", re.I), "특정대기유해물질"),
    (re.compile(r"특정\s*수질\s*유해\s*물질", re.I), "특정수질유해물질"),
    (re.compile(r"기후\s*생태\s*계\s*변화\s*유발\s*물질", re.I), "기후생태계변화유발물질"),
]


# ---------- rapidfuzz (있으면 사용, 없으면 폴백) ----------
try:
    from rapidfuzz import process, fuzz
    _HAS_FUZZ = True
except Exception:
    _HAS_FUZZ = False

def _fuzzy_norm(name: str) -> tuple[str, float]:
    """
    name을 표준 어휘(CANON_ITEMS) 중 하나로 정규화.
    - 사전 동의어 치환 → fuzzy 매칭
    - return: (정규화명, score). 매칭 실패 시 (원본, 0)
    """
    n = name
    # 1차: REGEX 동의어 치환
    for pat, repl in SYNONYM_MAP:
        if pat.search(n):
            return repl, 100.0

    # 2차: 숫자류(제n류) 간편 정규화
    m = re.search(r"제\s*([1-6])\s*류", n)
    if m:
        return f"제{m.group(1)}류", 95.0

    # 3차: fuzzy
    if _HAS_FUZZ:
        best = process.extractOne(
            n,
            CANON_ITEMS,
            scorer=fuzz.WRatio,  # 강건한 스코어러
        )
        if best and best[1] >= 80:
            return best[0], float(best[1])

    # 실패 폴백: 원본 그대로
    return n, 0.0


# ---------- 메인: 규제항목(only) 테이블 ----------
def build_legal_table(full_text: str, *, require_section15: bool = True) -> List[Dict[str, Any]]:
    """
    섹션 15 텍스트에서만 규제 '항목'을 추출(법규/관할 제거).
    반환 컬럼:
      section, item_code, item_name_raw, item_name, status, cas_ref, source, match_score
    """
    sec = _slice_sec15(full_text or "")
    if not sec:
        return [] if require_section15 else _extract_items(full_text or "")
    return _extract_items(sec)


def _extract_items(text: str) -> List[Dict[str, Any]]:
    # 줄/세미콜론 단위 분해
    chunks = [c.strip() for c in re.split(r"\n+|；|;", text) if c.strip()]
    rows: List[Dict[str, Any]] = []

    for ch in chunks:
        # 부가정보
        status_m = STATUS_PAT.search(ch)
        status = _norm_status(status_m.group(1) if status_m else None)
        cas_list = "; ".join(sorted(set(CAS_RE.findall(ch))))
        snippet = (ch[:300] + ("…" if len(ch) > 300 else ""))

        matched_line = False

        # 1) "코드 → 이름"
        for m in RE_CODE_NAME.finditer(ch):
            code = m.group(1).strip()
            raw = _clean_name(m.group(2))
            norm, score = _fuzzy_norm(raw)
            rows.append({
                "section": "15",
                "item_code": code,
                "item_name_raw": raw,
                "item_name": norm,
                "status": status,
                "cas_ref": cas_list,
                "source": snippet,
                "match_score": round(score, 1),
            })
            matched_line = True

        # 2) "이름 → 코드"
        if (not matched_line) and RE_CODE.search(ch):
            m2 = RE_NAME_CODE.search(ch)
            if m2:
                raw = _clean_name(m2.group(1))
                code = m2.group(2).strip()
                norm, score = _fuzzy_norm(raw)
                rows.append({
                    "section": "15",
                    "item_code": code,
                    "item_name_raw": raw,
                    "item_name": norm,
                    "status": status,
                    "cas_ref": cas_list,
                    "source": snippet,
                    "match_score": round(score, 1),
                })
                matched_line = True
            else:
                # 코드만 보이는 경우: 이름 공란으로 기록
                code = RE_CODE.search(ch).group(0)
                rows.append({
                    "section": "15",
                    "item_code": code,
                    "item_name_raw": "",
                    "item_name": "",
                    "status": status,
                    "cas_ref": cas_list,
                    "source": snippet,
                    "match_score": 0.0,
                })
                matched_line = True

        # 3) 코드가 없어도 이름 후보가 충분히 뚜렷하면 항목으로 기록
        if not matched_line:
            # 사전 동의어/숫자류 감지 또는 fuzzy 스코어가 충분히 높으면 기록
            raw = _clean_name(ch)
            norm, score = _fuzzy_norm(raw)
            if norm != raw or score >= 90:
                rows.append({
                    "section": "15",
                    "item_code": "",     # 코드 미기재
                    "item_name_raw": raw,
                    "item_name": norm,
                    "status": status,
                    "cas_ref": cas_list,
                    "source": snippet,
                    "match_score": round(score if score else 90.0, 1),
                })

    # 중복 제거
    uniq: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        key = (r["item_code"], r["item_name"], r["status"], r["source"][:80])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    return uniq
