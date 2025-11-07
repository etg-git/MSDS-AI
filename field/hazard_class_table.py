# field/hazard_class_table.py
# Section 2 (유해성·위험성) → 분류/구분 표 생성 (Regex + RapidFuzz)
# 변경점:
#  - 섹션2 텍스트에서만 추출 (slicing 고정)
#  - "피부 부식/자극" 통합
#  - "눈 손상/자극" 통합
#  - "폭발물" 동의어 대폭 확장
from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple

try:
    from rapidfuzz import fuzz, process
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False

# =========================================================
# 1) Section 2 슬라이스 (여기서만 추출)
# =========================================================
SEC2_START = re.compile(
    r"(?:^|\n)\s*(?:2\.|제\s*2\s*장)\s*"
    r"(?:유해성[·\.\s]*위험성|유해성\s*[ㆍ\.]\s*위험성|위험성\s*[ㆍ\.]\s*유해성|Hazards?\s*identification)\b",
    re.IGNORECASE
)
SEC2_END = re.compile(
    r"(?:^|\n)\s*(?:3\.|제\s*3\s*장)\s*"
    r"(?:구성성분|성분|조성|Composition|Information\s*on\s*ingredients)\b",
    re.IGNORECASE
)

def _slice_sec2(full_text: str, fallback_len: int = 2600) -> str:
    if not full_text:
        return ""
    m = SEC2_START.search(full_text)
    if not m:
        m2 = re.search(r"(유해성|위험성|hazard)", full_text, re.IGNORECASE)
        if m2:
            s = max(0, m2.start() - 400)
            e = min(len(full_text), m2.start() + 1200)
            return full_text[s:e]
        return ""
    m_end = SEC2_END.search(full_text, m.end())
    end = m_end.start() if m_end else min(len(full_text), m.start() + fallback_len)
    return full_text[m.start(): end]

# =========================================================
# 2) 표준 분류 사전
#    canonical key: (group, eng, kor)
#    ※ 피부 부식/자극, 눈 손상/자극: 각각 단일 클래스로 통합
# =========================================================
def _ck(g: str, e: str, k: str) -> Tuple[str, str, str]:
    return (g, e, k)

PHYSICAL = "Physical"
HEALTH = "Health"
ENV = "Environmental"

CANONICAL_CLASSES: List[Tuple[Tuple[str, str, str], List[str]]] = [
    # --- Physical hazards ---
    (_ck(PHYSICAL, "Explosives", "폭발물"), [
        r"폭발물", r"폭발\s*성\s*물질", r"폭발\s*성", r"폭발\s*위험", r"폭발성\s*고체", r"폭발성\s*물질",
        r"\bexplosive\b", r"\bexplosives\b", r"explosion\s*hazard", r"explosive\s*substance",
        r"폭발\s*위험\s*물질", r"폭발\s*가능성", r"폭발\s*성분"
    ]),
    (_ck(PHYSICAL, "Flammable gases", "인화성 가스"), [
        r"인화성\s*가스", r"\bflammable\s*gases?\b"
    ]),
    (_ck(PHYSICAL, "Aerosols", "에어로졸"), [
        r"에어로졸", r"\baerosols?\b", r"분무제"
    ]),
    (_ck(PHYSICAL, "Oxidizing gases", "산화성 가스"), [
        r"산화성\s*가스", r"oxidiz(?:ing|ing)\s*gases?"
    ]),
    (_ck(PHYSICAL, "Gases under pressure", "고압가스"), [
        r"고압\s*가스", r"압축\s*가스", r"\bgases\s*under\s*pressure\b",
        r"liquefied\s*gas", r"refrigerated\s*liquefied\s*gas", r"dissolved\s*gas"
    ]),
    (_ck(PHYSICAL, "Flammable liquids", "인화성 액체"), [
        r"인화성\s*액체", r"\bflammable\s*liquids?\b"
    ]),
    (_ck(PHYSICAL, "Flammable solids", "인화성 고체"), [
        r"인화성\s*고체", r"\bflammable\s*solids?\b"
    ]),
    (_ck(PHYSICAL, "Self-reactive substances and mixtures", "자기반응성 물질/혼합물"), [
        r"자기\s*반응성", r"\bself[-\s]*reactive\b"
    ]),
    (_ck(PHYSICAL, "Pyrophoric liquids", "자연발화성(피로포릭) 액체"), [
        r"자연\s*발화\s*성\s*액체", r"\bpyrophoric\s*liquids?\b"
    ]),
    (_ck(PHYSICAL, "Pyrophoric solids", "자연발화성(피로포릭) 고체"), [
        r"자연\s*발화\s*성\s*고체", r"\bpyrophoric\s*solids?\b"
    ]),
    (_ck(PHYSICAL, "Self-heating substances and mixtures", "자기발열성 물질/혼합물"), [
        r"자기\s*발열\s*성", r"\bself[-\s]*heating\b"
    ]),
    (_ck(PHYSICAL, "Substances which, in contact with water, emit flammable gases",
         "물반응성 가연성 가스 발생물질"), [
        r"물\s*반응\s*성", r"water[-\s]*reactive", r"물과\s*반응하여\s*가연성\s*가스"
    ]),
    (_ck(PHYSICAL, "Oxidizing liquids", "산화성 액체"), [
        r"산화성\s*액체", r"oxidiz(?:ing|ing)\s*liquids?"
    ]),
    (_ck(PHYSICAL, "Oxidizing solids", "산화성 고체"), [
        r"산화성\s*고체", r"oxidiz(?:ing|ing)\s*solids?"
    ]),
    (_ck(PHYSICAL, "Organic peroxides", "유기과산화물"), [
        r"유기\s*과산화물", r"\borganic\s*peroxides?\b"
    ]),
    (_ck(PHYSICAL, "Corrosive to metals", "금속부식성"), [
        r"금속\s*부식\s*성", r"\bcorrosive\s*to\s*metals\b"
    ]),

    # --- Health hazards ---
    (_ck(HEALTH, "Acute toxicity (oral)", "급성 독성(경구)"), [
        r"급성\s*독성.*경구", r"acute.*toxicity.*oral"
    ]),
    (_ck(HEALTH, "Acute toxicity (dermal)", "급성 독성(경피)"), [
        r"급성\s*독성.*경피", r"acute.*toxicity.*dermal"
    ]),
    (_ck(HEALTH, "Acute toxicity (inhalation)", "급성 독성(흡입)"), [
        r"급성\s*독성.*흡입", r"acute.*toxicity.*inhalation"
    ]),
    # ★ 통합: Skin corrosion/irritation
    (_ck(HEALTH, "Skin corrosion/irritation", "피부 부식/자극"), [
        r"피부\s*부식", r"피부\s*자극", r"\bskin\s*corrosion\b", r"\bskin\s*irritation\b",
        r"피부\s*부식성", r"피부\s*자극성", r"부식/자극"
    ]),
    # ★ 통합: Eye damage/irritation
    (_ck(HEALTH, "Eye damage/irritation", "눈 손상/자극"), [
        r"심한\s*눈\s*손상", r"눈\s*손상", r"눈\s*자극", r"\beye\s*damage\b", r"\beye\s*irritation\b",
        r"눈\s*손상성", r"눈\s*자극성"
    ]),
    (_ck(HEALTH, "Respiratory sensitization", "호흡 과민화"), [
        r"호흡\s*과민화", r"resp(\.|iratory)?\s*sensiti"
    ]),
    (_ck(HEALTH, "Skin sensitization", "피부 과민화"), [
        r"피부\s*과민화", r"\bskin\s*sensiti"
    ]),
    (_ck(HEALTH, "Germ cell mutagenicity", "생식세포 변이원성"), [
        r"생식세포\s*변이원성", r"mutagenicity"
    ]),
    (_ck(HEALTH, "Carcinogenicity", "발암성"), [
        r"발암성", r"carcinogen"
    ]),
    (_ck(HEALTH, "Reproductive toxicity", "생식독성"), [
        r"생식독성", r"reproductive\s*tox"
    ]),
    (_ck(HEALTH, "STOT — Single exposure", "특정 표적장기 독성(1회 노출)"), [
        r"특정\s*표적장기\s*독성.*1회", r"stot\s*se"
    ]),
    (_ck(HEALTH, "STOT — Repeated exposure", "특정 표적장기 독성(반복 노출)"), [
        r"특정\s*표적장기\s*독성.*반복", r"stot\s*re"
    ]),
    (_ck(HEALTH, "Aspiration hazard", "흡인 유해성"), [
        r"흡인\s*유해성", r"aspiration\s*hazard"
    ]),

    # --- Environmental hazards ---
    (_ck(ENV, "Hazardous to the aquatic environment (acute)", "수생환경 유해성(급성)"), [
        # 한글: "수생환경 유해성(급성)" / "급성 수생환경 유해성" / 공백·괄호 변형 모두 허용
        r"(수생\s*환경.*유해.*급성)|(급성.*수생\s*환경.*유해)",
        # 축약/변형
        r"수생.*급성", r"수서.*급성",  # 일부 문서에 '수서' 표기 케이스
        # 영문: order-insensitive
        r"(aquatic.*acute.*hazard)|(acute.*aquatic.*hazard)",
        r"\bhazardous\s*to\s*the\s*aquatic\s*environment\b.*\b(acute)\b",
        r"\b(acute)\b.*\bhazardous\s*to\s*the\s*aquatic\s*environment\b"
    ]),

    (_ck(ENV, "Hazardous to the aquatic environment (chronic)", "수생환경 유해성(만성)"), [
        r"(수생\s*환경.*유해.*만성)|(만성.*수생\s*환경.*유해)",
        r"수생.*만성", r"수서.*만성",
        r"(aquatic.*chronic.*hazard)|(chronic.*aquatic.*hazard)",
        r"\bhazardous\s*to\s*the\s*aquatic\s*environment\b.*\b(chronic)\b",
        r"\b(chronic)\b.*\bhazardous\s*to\s*the\s*aquatic\s*environment\b"
    ]),
    (_ck(ENV, "Hazardous to the ozone layer", "오존층 유해성"), [
        r"오존층\s*유해성", r"ozone\s*layer"
    ]),
]

# =========================================================
# 3) 카테고리 파싱/비교
# =========================================================
CAT_RE = re.compile(r"(?:구분|Category)\s*[:\-]?\s*([0-9]+[A-C]?)", re.IGNORECASE)

def _rank(cat: str) -> Tuple[int, str]:
    c = (cat or "").upper().strip()
    if not c:
        return (9999, "")
    m = re.match(r"(\d+)([A-C]?)", c)
    if not m:
        return (9999, c)
    base = int(m.group(1))
    suf = m.group(2)
    bonus = {"": 0, "A": 1, "B": 2, "C": 3}.get(suf, 4)
    return (base * 10 + bonus, c)

def _best(a: str, b: str) -> str:
    return a if _rank(a) < _rank(b) else b

# =========================================================
# 4) H코드 → 보조 근거(카테고리 추정은 하지 않음)
# =========================================================
H_RE = re.compile(r"\b(H\d{3}[A-Z]?)\b", re.I)
H_TO_CLASS = {
    # Skin corrosion/irritation: 통합
    "H314": _ck(HEALTH, "Skin corrosion/irritation", "피부 부식/자극"),
    "H315": _ck(HEALTH, "Skin corrosion/irritation", "피부 부식/자극"),
    # Eye damage/irritation: 통합
    "H318": _ck(HEALTH, "Eye damage/irritation", "눈 손상/자극"),
    "H319": _ck(HEALTH, "Eye damage/irritation", "눈 손상/자극"),
    # Sensitization
    "H334": _ck(HEALTH, "Respiratory sensitization", "호흡 과민화"),
    "H317": _ck(HEALTH, "Skin sensitization", "피부 과민화"),
    # STOT
    "H335": _ck(HEALTH, "STOT — Single exposure", "특정 표적장기 독성(1회 노출)"),
    "H336": _ck(HEALTH, "STOT — Single exposure", "특정 표적장기 독성(1회 노출)"),
    "H370": _ck(HEALTH, "STOT — Single exposure", "특정 표적장기 독성(1회 노출)"),
    "H371": _ck(HEALTH, "STOT — Single exposure", "특정 표적장기 독성(1회 노출)"),
    "H372": _ck(HEALTH, "STOT — Repeated exposure", "특정 표적장기 독성(반복 노출)"),
    "H373": _ck(HEALTH, "STOT — Repeated exposure", "특정 표적장기 독성(반복 노출)"),
    # CMR
    "H350": _ck(HEALTH, "Carcinogenicity", "발암성"),
    "H351": _ck(HEALTH, "Carcinogenicity", "발암성"),
    "H340": _ck(HEALTH, "Germ cell mutagenicity", "생식세포 변이원성"),
    "H341": _ck(HEALTH, "Germ cell mutagenicity", "생식세포 변이원성"),
    "H360": _ck(HEALTH, "Reproductive toxicity", "생식독성"),
    "H361": _ck(HEALTH, "Reproductive toxicity", "생식독성"),
    # Aspiration
    "H304": _ck(HEALTH, "Aspiration hazard", "흡인 유해성"),
    # Acute tox
    "H300": _ck(HEALTH, "Acute toxicity (oral)", "급성 독성(경구)"),
    "H301": _ck(HEALTH, "Acute toxicity (oral)", "급성 독성(경구)"),
    "H302": _ck(HEALTH, "Acute toxicity (경구)", "급성 독성(경구)"),
    "H310": _ck(HEALTH, "Acute toxicity (dermal)", "급성 독성(경피)"),
    "H311": _ck(HEALTH, "Acute toxicity (dermal)", "급성 독성(경피)"),
    "H312": _ck(HEALTH, "Acute toxicity (dermal)", "급성 독성(경피)"),
    "H330": _ck(HEALTH, "Acute toxicity (inhalation)", "급성 독성(흡입)"),
    "H331": _ck(HEALTH, "Acute toxicity (inhalation)", "급성 독성(흡입)"),
    "H332": _ck(HEALTH, "Acute toxicity (inhalation)", "급성 독성(흡입)"),
    # Environmental
    "H400": _ck(ENV, "Hazardous to the aquatic environment (acute)", "수생환경 유해성(급성)"),
    "H410": _ck(ENV, "Hazardous to the aquatic environment (chronic)", "수생환경 유해성(만성)"),
    "H411": _ck(ENV, "Hazardous to the aquatic environment (chronic)", "수생환경 유해성(만성)"),
    "H412": _ck(ENV, "Hazardous to the aquatic environment (chronic)", "수생환경 유해성(만성)"),
    "H413": _ck(ENV, "Hazardous to the aquatic environment (chronic)", "수생환경 유해성(만성)"),
}

# =========================================================
# 5) 매칭 엔진 (regex 우선, fuzzy 보조)
# =========================================================
CANON_KEYS: List[Tuple[str, str, str]] = [c[0] for c in CANONICAL_CLASSES]
SYN_INDEX: List[Tuple[str, Tuple[str, str, str]]] = []
for (canon, syns) in CANONICAL_CLASSES:
    for s in syns:
        SYN_INDEX.append((s, canon))

def _regex_hit(line: str) -> Tuple[Tuple[str,str,str], str] | None:
    for syn, canon in SYN_INDEX:
        pat = re.compile(syn, re.IGNORECASE)
        if pat.search(line):
            return (canon, syn)
    return None

def _fuzzy_hit(line: str, threshold: int = 88) -> Tuple[Tuple[str,str,str], str] | None:
    if not _HAS_RAPIDFUZZ:
        return None
    probe = line[:200]
    choices = [syn for syn, _ in SYN_INDEX]
    best = process.extractOne(probe, choices, scorer=fuzz.token_set_ratio)
    if best and best[1] >= threshold:
        syn = best[0]
        for s, canon in SYN_INDEX:
            if s == syn:
                return (canon, syn)
    return None

def _parse_category(line: str) -> str:
    m = CAT_RE.search(line)
    return m.group(1).upper() if m else ""

# =========================================================
# 6) 메인: build_hazard_class_table
# =========================================================
def build_hazard_class_table(full_text: str) -> List[Dict[str, Any]]:
    """
    섹션 2에서 '분류/구분' 표 생성.
    컬럼: hazard_group, hazard_class_eng, hazard_class_kor, category,
          basis(Text-regex/Text-fuzzy/H-codes), matched_term, hcodes, source, section
    """
    sec2 = _slice_sec2(full_text or "")
    if not sec2:
        return []

    # 라인/세미콜론 기준 분해
    chunks = [c.strip() for c in re.split(r"\n+|；|;", sec2) if c.strip()]

    found: Dict[Tuple[str,str,str], Dict[str, Any]] = {}

    # 6.1 텍스트 기반: regex → fuzzy
    for ch in chunks:
        hit = _regex_hit(ch)
        basis = ""
        syn_used = ""
        if hit:
            canon, syn_used = hit
            basis = "Text-regex"
        else:
            hit = _fuzzy_hit(ch)
            if hit:
                canon, syn_used = hit
                basis = "Text-fuzzy"
            else:
                canon = None

        if canon:
            cat = _parse_category(ch)
            key = canon
            cur = found.get(key, {
                "hazard_group": key[0],
                "hazard_class_eng": key[1],
                "hazard_class_kor": key[2],
                "category": "",
                "basis": basis,
                "matched_term": syn_used,
                "hcodes": set(),
                "source": ch[:300] + ("…" if len(ch) > 300 else ""),
                "section": "2",
            })
            if cat:
                cur["category"] = _best(cur["category"], cat) if cur["category"] else cat
            # basis 우선순위: Text-regex > Text-fuzzy > H-codes
            if cur.get("basis") != "Text-regex" and basis == "Text-regex":
                cur["basis"] = "Text-regex"
            if not cur.get("matched_term"):
                cur["matched_term"] = syn_used
            found[key] = cur

    # 6.2 H코드 보조: 카테고리는 추정 안 함(섹션2표는 보통 텍스트에 명시)
    hset = set(h.upper() for h in H_RE.findall(sec2))
    for h in sorted(hset):
        canon = H_TO_CLASS.get(h)
        if not canon:
            continue
        key = canon
        cur = found.get(key, {
            "hazard_group": key[0],
            "hazard_class_eng": key[1],
            "hazard_class_kor": key[2],
            "category": "",
            "basis": "H-codes",
            "matched_term": h,
            "hcodes": set(),
            "source": h,
            "section": "2",
        })
        cur["hcodes"].add(h)
        # basis 유지 규칙: Text-regex > Text-fuzzy > H-codes
        if cur.get("basis") in ("Text-regex", "Text-fuzzy"):
            pass
        else:
            cur["basis"] = "H-codes"
        found[key] = cur

    # 마무리
    rows: List[Dict[str, Any]] = []
    for key, r in found.items():
        r["hcodes"] = ", ".join(sorted(r["hcodes"])) if r.get("hcodes") else ""
        if not r.get("category"):
            r["category"] = "-"
        rows.append(r)

    # 정렬: Group → Class(영문) → Category severity
    def _sort_key(x):
        g = {"Physical":0, "Health":1, "Environmental":2}.get(x["hazard_group"], 9)
        return (g, x["hazard_class_eng"], _rank(x.get("category",""))[0])

    return sorted(rows, key=_sort_key)
