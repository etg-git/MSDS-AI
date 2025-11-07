# msds_section_splitter.py
# 동적 섹션 분리: 제목 후보 탐지 → 동의어/퍼지매칭으로 GHS 캐논키에 매핑
from __future__ import annotations
from typing import Dict, List, Tuple, Any, Optional
import re
import os
import yaml

# ---- 캐논 키 번호 맵 (KOSHA 번호 → 캐논)
NUM_TO_CANON: Dict[str, str] = {
    '1':'identification','2':'hazards','3':'composition','4':'first_aid',
    '5':'fire_fighting','6':'accidental_release','7':'handling_storage',
    '8':'exposure_ppe','9':'physical_chemical','10':'stability_reactivity',
    '11':'toxicology','12':'ecology','13':'disposal','14':'transport',
    '15':'regulation','16':'other'
}

# ---- 동의어/용어 로딩 (사용자 프로젝트에 있으면 사용, 없으면 기본값)
try:
    from section.msds_header_lexicon import GHS_TERMS, BASE_SYNONYMS
except Exception:
    # 최소 동작 보장을 위한 기본값
    GHS_TERMS = [
        'identification','hazards','composition','first_aid','fire_fighting',
        'accidental_release','handling_storage','exposure_ppe','physical_chemical',
        'stability_reactivity','toxicology','ecology','disposal','transport',
        'regulation','other'
    ]
    BASE_SYNONYMS = {
        'identification': ['제품 정보','제품 식별','화학제품과 회사에 관한 정보','식별','identifier','identification','supplier','회사 정보','제조사 정보'],
        'hazards': ['유해성','위험성','표시사항','경고표지','GHS','hazard','hazards','label'],
        'composition': ['구성성분','성분','조성','ingredient','composition'],
        'first_aid': ['응급조치','응급조치요령','first aid'],
        'fire_fighting': ['폭발·화재','화재시 대처','소화','fire fighting','fire-fighting'],
        'accidental_release': ['누출사고','유출사고','accidental release'],
        'handling_storage': ['취급 및 저장','저장방법','취급','handling','storage','handling and storage'],
        'exposure_ppe': ['노출기준','개인보호구','공학적 관리','exposure','ppe','personal protection'],
        'physical_chemical': ['물리화학적 특성','물리적 성질','화학적 성질','physical and chemical','physical properties'],
        'stability_reactivity': ['안정성 및 반응성','stability','reactivity'],
        'toxicology': ['독성에 관한 정보','toxicological','toxicology'],
        'ecology': ['환경에 미치는 영향','생태','ecological','ecotoxicity'],
        'disposal': ['폐기시 주의사항','처분','disposal'],
        'transport': ['운송에 필요한 정보','transport'],
        'regulation': ['규제 정보','법규','regulatory','regulation'],
        'other': ['기타 참고사항','참고','other','reference','기타']
    }

# ---- 퍼지 매칭(rapidfuzz가 있으면 사용)
try:
    from rapidfuzz import process, fuzz
    _HAS_RAPID = True
except Exception:
    _HAS_RAPID = False

# ======================================================================
# 내부 유틸
# ======================================================================

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
    # ./config/synonyms.yml 이 있으면 사용자 동의어 병합
    path = os.path.join("config", "synonyms.yml")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {k: list(v or []) for k, v in data.items() if k in GHS_TERMS}
    except Exception:
        return {}

def _build_search_space() -> Dict[str, List[str]]:
    merged = {k: list(v) for k, v in BASE_SYNONYMS.items()}
    user = _load_user_synonyms()
    for k, vs in user.items():
        merged.setdefault(k, [])
        merged[k].extend(vs)
    # 중복 제거(소문자 기준)
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
    # 제목 후보: 길이 4~80, 지나치게 본문같은 패턴 배제
    if not (4 <= len(line) <= 80):
        return False
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
        # 2) "제목: 본문" 라인 → 콜론 앞까지 제목 후보
        if ":" in ln:
            prefix = ln.split(":", 1)[0].strip()
            if _is_short_title(prefix):
                cands.append((i, prefix, None))
                continue
        # 3) 그 외 짧은 한 줄
        if _is_short_title(ln):
            cands.append((i, ln, None))
    return cands

def _collect_numbered_headers(lines: List[str]) -> List[Tuple[int, str, str]]:
    """
    KOSHA 스타일: "1. 제목" 형태만 추출
    return: [(line_index, canon_key, raw_title), ...]
    """
    headers: List[Tuple[int, str, str]] = []
    seen = set()
    for i, ln in enumerate(lines):
        m = KOSHA_HEADER_RE.match(ln)
        if not m:
            continue
        num = m.group("num")
        raw = m.group("title").strip(" :")
        canon = NUM_TO_CANON.get(num)
        if not canon or canon in seen:
            continue
        seen.add(canon)
        headers.append((i, canon, raw))
    return headers

def _map_title_to_canon(raw_title: str, num_hint: Optional[str]) -> Optional[str]:
    """
    제목(raw_title) 또는 숫자 힌트(num_hint)를 가지고 캐논 키 추정
    """
    lt = raw_title.lower().strip()

    # 숫자 힌트 우선
    if num_hint and num_hint in NUM_TO_CANON:
        return NUM_TO_CANON[num_hint]

    # 직관적 포함 매칭
    for canon, terms in SEARCH_SPACE.items():
        for t in terms:
            if t.lower() in lt:
                return canon

    # 퍼지 매칭(옵션)
    if _HAS_RAPID:
        # 검색 풀: (canon, term)
        pool: List[Tuple[str, str]] = []
        for canon, terms in SEARCH_SPACE.items():
            for t in terms:
                pool.append((canon, t))
        # label 텍스트 전체로 유사도 비교
        candidates = process.extract(
            lt,
            {i: term for i, (_, term) in enumerate(pool)},
            scorer=fuzz.WRatio,
            limit=5
        )
        for choice, score, idx in candidates:
            if score >= 86:
                canon = pool[idx][0]
                return canon

    return None

# ======================================================================
# 엔트리: split_sections_auto
# ======================================================================

def split_sections_auto(full_text: str, pdf_path: str | None = None):
    """
    반환 구조:
    sections: Dict[str, Dict]  # 키는 항상 '캐논 키'만 (숫자 키 절대 생성 X)
        {
          "identification": {"title": "...원문 헤더...", "text": "..."},
          "hazards": {"title": "...", "text": "..."},
          ...
        }
    logs: List[str]
    template: "KOSHA" | "VENDOR"
    """
    lines = _normalize_lines(full_text)
    template = _detect_template(full_text)

    logs: List[str] = []
    headers: List[tuple[int, str, str]] = []

    # 1) 번호형(KOSHA) 먼저 시도
    num_headers = _collect_numbered_headers(lines)
    if len(num_headers) >= 8:
        logs.append(f"[섹션] 번호형(KOSHA) 헤더 {len(num_headers)}개 감지 → 번호 기반 매핑을 우선 적용.")
        headers = sorted(num_headers, key=lambda x: x[0])
    else:
        # 2) 번호형 부족 → 후보 탐지 + 캐논 매핑
        cands = _collect_header_candidates(lines)
        seen_canon = set()
        best: List[Tuple[int, str, str]] = []
        for idx, raw_title, num_hint in cands:
            canon = _map_title_to_canon(raw_title, num_hint)
            if not canon or canon in seen_canon:
                continue
            seen_canon.add(canon)
            best.append((idx, canon, raw_title))
        headers = sorted(best, key=lambda x: x[0])
        logs.append(f"[섹션] 퍼지/키워드 기반 헤더 {len(headers)}개 감지.")

    if not headers:
        logs.append("[섹션] 유효 헤더를 찾지 못함 → 전체 본문을 'other'로 반환.")
        return ({"other": {"title": "기타", "text": "\n".join(lines)}}, logs, template)

    # 3) 본문 슬라이싱 (패치 2: 키를 'canon'으로만 저장)
    sections: Dict[str, Dict[str, Any]] = {}
    for j, (start_i, canon, raw) in enumerate(headers):
        end_i = headers[j+1][0] if (j+1 < len(headers)) else len(lines)
        body_lines = lines[start_i+1:end_i]

        # "제목: 본문" 한 줄 보정 → 콜론 뒤를 본문 선행으로 삽입
        orig_line = lines[start_i]
        if ":" in orig_line and orig_line.lower().startswith(raw.lower()):
            tail = orig_line.split(":", 1)[1].strip()
            if tail:
                body_lines = [tail] + body_lines

        # 여기! 숫자키 생성 없이 'canon' 키로만 저장
        sections[canon] = {
            "title": raw,
            "text": "\n".join(body_lines).strip(),
            # 참고: 내부 디버깅 메타(필요 없다면 삭제 가능)
            "canon": canon,
            "source": "text",
            "_start": start_i,
        }

    logs.append(f"[섹션] 템플릿 추정: {template}. 최종 섹션 수={len(sections)}")
    logs.append("[섹션] 감지 순서: " + ", ".join([c for _, c, _ in headers]))
    return sections, logs, template
