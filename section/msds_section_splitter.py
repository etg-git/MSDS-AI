# msds_section_splitter.py
# 동적 섹션 분리: 제목 후보 탐지 → 동의어/퍼지매칭으로 GHS 캐논키에 매핑

from typing import Dict, List, Tuple, Any, Optional
import re
import os
import yaml

from section.msds_header_lexicon import GHS_TERMS, BASE_SYNONYMS

NUM_TO_CANON = {
    '1':'identification','2':'hazards','3':'composition','4':'first_aid',
    '5':'fire_fighting','6':'accidental_release','7':'handling_storage',
    '8':'exposure_ppe','9':'physical_chemical','10':'stability_reactivity',
    '11':'toxicology','12':'ecology','13':'disposal','14':'transport',
    '15':'regulation','16':'other'
}# 목적: 문서에서 섹션 헤더 후보를 찾고 16개 내외 블록으로 분리
# 규칙: 한국어/영어 키워드 혼합, 숫자 점/괄호 패턴 허용, 헤더 라인 길이 제한 등
import re
from typing import Dict, Tuple, List

# 헤더 패턴(대표 키워드)
HEADER_KEYS = [
    "제품명","식별자","공급자","제조사","성분","구성성분","조성",
    "유해성","위험성","표시사항","경고문구","주의문구","그림문자","신호어",
    "응급조치","화재진압","누출대응","사고","처치","폭발",
    "취급","저장","안전","노출기준","개인보호구","보호장비",
    "물리화학적 성질","물리적 화학적 성질","물리적 성질",
    "안정성","반응성","독성","생태","폐기","운송","규제","기타","참고",
    "identification","supplier","composition","hazard","label","signal",
    "first aid","fire-fighting","accidental release","handling","storage",
    "exposure","ppe","physical","stability","reactivity","toxicology",
    "ecological","disposal","transport","regulatory","other","reference"
]


HEADER_LINE = re.compile(
    r"^\s*(\d{1,2}[\.\)]\s*)?([A-Za-z가-힣\-/\s]{2,60})\s*$"
)

def _is_header_line(ln: str) -> bool:
    """한 줄이 헤더로 보이는지 간단 검증"""
    if len(ln) > 80: 
        return False
    m = HEADER_LINE.match(ln)
    if not m:
        return False
    low = ln.lower()
    return any(k in low for k in [k.lower() for k in HEADER_KEYS])

def split_sections_auto(text: str) -> Tuple[Dict[str, Dict], List[str], Dict]:
    """
    문서 전체를 줄 단위로 훑어 헤더 후보를 모으고 섹션 블록 생성
    return: sections dict, logs, template(dict: 추후 매핑 템플릿 용)
    """
    logs: List[str] = []
    lines = [ln.rstrip() for ln in text.splitlines()]
    headers: List[Tuple[int,str]] = []
    for i, ln in enumerate(lines):
        if _is_header_line(ln):
            headers.append((i, ln.strip()))
    # 헤더 없으면 전체를 하나의 섹션으로
    if not headers:
        return {"full": {"title": "full", "text": text}}, ["헤더를 찾지 못했습니다."], {}

    # 본문 블록 만들기
    sections: Dict[str, Dict] = {}
    for idx, (row, title) in enumerate(headers):
        start = row + 1
        end = headers[idx+1][0] if idx+1 < len(headers) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        key = f"sec_{idx+1:02d}"
        sections[key] = {"title": title, "text": body}

    logs.append(f"헤더 {len(headers)}개를 감지했습니다.")
    return sections, logs, {}


KOSHA_HEADER_RE = re.compile(r'^\s*(?P<num>\d{1,2})\.\s*(?P<title>.+?)\s*$', re.IGNORECASE)

def _normalize_lines(text: str) -> List[str]:
    text = text.replace("\r", "")
    lines = text.split("\n")
    return [re.sub(r"[ \t]+", " ", ln.strip()) for ln in lines]

def _detect_template(text: str) -> str:
    t = text.upper()
    kosha_hit = ("KOSHA" in t) or ("산업안전보건공단" in text)
    numbered = len(re.findall(r'^\s*\d{1,2}\.\s+', text, flags=re.MULTILINE)) >= 8
    return "KOSHA" if (kosha_hit or numbered) else "VENDOR"

def _load_user_synonyms() -> Dict[str, List[str]]:
    # ./config/synonyms.yml 이 있으면 덮어쓰기
    path = os.path.join("config", "synonyms.yml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # {canon_key: [synonym1, synonym2, ...]}
        return {k: list(v or []) for k, v in data.items() if k in GHS_TERMS}
    except Exception:
        return {}

def _build_search_space() -> Dict[str, List[str]]:
    # 기본 동의어 + 사용자 사전 병합
    merged = {k: list(v) for k, v in BASE_SYNONYMS.items()}
    user = _load_user_synonyms()
    for k, vs in user.items():
        merged.setdefault(k, [])
        merged[k].extend(vs)
    # 중복 제거, 소문자 비교 기준
    for k in merged:
        seen, uniq = set(), []
        for term in merged[k]:
            key = term.strip().lower()
            if key and key not in seen:
                seen.add(key)
                uniq.append(term)
        merged[k] = uniq
    return merged

SEARCH_SPACE = _build_search_space()

def _is_short_title(line: str) -> bool:
    # 제목 후보: 길이 4~80, 문장부호 위주로 끝나지 않음
    if not (4 <= len(line) <= 80):
        return False
    # 본문처럼 보이는 패턴 배제(마침표 2개 이상, 콜론 뒤에 본문 등)
    if line.count(".") > 3:
        return False
    return True

def _collect_header_candidates(lines: List[str]) -> List[Tuple[int, str, Optional[str]]]:
    """
    제목 후보 수집
    return: list of (line_idx, raw_title, numeric_hint)
    """
    cands: List[Tuple[int, str, Optional[str]]] = []
    for i, ln in enumerate(lines):
        # 1) "N. 제목" 형태
        m = KOSHA_HEADER_RE.match(ln)
        if m:
            num = m.group("num")
            title = m.group("title").strip(" :")
            cands.append((i, title, num))
            continue
        # 2) 콜론 뒤 내용 시작하는 라인: "제목: ..."(짧은 제목)
        if ":" in ln:
            prefix = ln.split(":", 1)[0].strip()
            if _is_short_title(prefix):
                cands.append((i, prefix, None))
                continue
        # 3) 그 외 짧은 한 줄 제목
        if _is_short_title(ln):
            cands.append((i, ln, None))
    return cands

def _collect_numbered_headers(lines: List[str]) -> List[Tuple[int, str, str]]:
    """
    KOSHA 스타일: "1. 제목" 형태만 추출
    return: [(line_index, canon_key, raw_title), ...]  (숫자 → canon 매핑 성공한 것만)
    """
    headers = []
    seen = set()
    for i, ln in enumerate(lines):
        m = KOSHA_HEADER_RE.match(ln)
        if not m:
            continue
        num = m.group("num")
        raw = m.group("title").strip(" :")
        canon = NUM_TO_CANON.get(num)
        if not canon:
            continue
        if canon in seen:
            continue
        seen.add(canon)
        headers.append((i, canon, raw))
    return headers

def split_sections_auto(full_text: str):
    lines = _normalize_lines(full_text)
    template = _detect_template(full_text)

    logs = []
    headers: List[Tuple[int, str, str]] = []

    # 2-1) 번호형을 먼저 시도: 8개 이상 감지되면 이걸 우선 사용
    num_headers = _collect_numbered_headers(lines)
    if len(num_headers) >= 8:
        logs.append(f"[섹션] 번호형(KOSHA) 헤더 {len(num_headers)}개 감지 → 번호 기반 매핑을 우선 적용.")
        headers = sorted(num_headers, key=lambda x: x[0])
    else:
        # 2-2) 번호형이 부족하면 기존 동적 후보 + 퍼지 매칭
        cands = _collect_header_candidates(lines)
        seen_canon = set()
        best: List[Tuple[int, str, str]] = []
        for idx, raw_title, num_hint in cands:
            canon = _map_title_to_canon(raw_title, num_hint)
            if not canon:
                continue
            if canon in seen_canon:
                continue
            seen_canon.add(canon)
            best.append((idx, canon, raw_title))
        headers = sorted(best, key=lambda x: x[0])
        logs.append(f"[섹션] 퍼지매칭 헤더 {len(headers)}개 감지.")

    if not headers:
        logs.append("[섹션] 유효 헤더를 찾지 못함 → 전체 본문을 '기타'로 반환.")
        return ({"other": {"title": "기타", "text": "\n".join(lines)}}, logs, template)

    # 2-3) 본문 슬라이싱
    sections: Dict[str, Dict[str, Any]] = {}
    for j, (start_i, canon, raw) in enumerate(headers):
        end_i = headers[j+1][0] if (j+1 < len(headers)) else len(lines)
        body_lines = lines[start_i+1:end_i]

        # "제목: 본문" 한 줄 형식 보정
        orig_line = lines[start_i]
        if ":" in orig_line and orig_line.strip().lower().startswith(raw.lower()):
            tail = orig_line.split(":", 1)[1].strip()
            if tail:
                body_lines = [tail] + body_lines

        sections[canon] = {"title": raw, "text": "\n".join(body_lines).strip()}

    logs.append(f"[섹션] 템플릿 추정: {template}. 최종 섹션 수={len(sections)}")
    logs.append("[섹션] 감지 순서: " + ", ".join([c for _, c, _ in headers]))
    return sections, logs, template
