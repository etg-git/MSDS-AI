# ghs_pictogram_mapper.py
# H-codes -> GHS pictograms with category-aware precedence
# public API:
#   map_hcodes_to_pictos(hcodes, policy=None) -> {"pictograms":[...], "labels":[...]}
#   map_hcodes_to_pictos_detailed(hcodes, policy=None) -> [{"pictogram","label","triggers","rule_notes"}...]

from typing import Iterable, Dict, List, Set, Tuple

# ---------- 기본 라벨 ----------
PICTO_LABEL: Dict[str, str] = {
    "GHS01": "Exploding bomb (폭발물)",
    "GHS02": "Flame (화염)",
    "GHS03": "Flame over circle (산화성)",
    "GHS04": "Gas cylinder (가스통)",
    "GHS05": "Corrosion (부식)",
    "GHS06": "Skull and crossbones (급성독성 Cat.1–3)",
    "GHS07": "Exclamation mark (자극/급성독성 Cat.4 등)",
    "GHS08": "Health hazard (장기독성/발암/흡인유해 등)",
    "GHS09": "Environment (수생환경 유해)",
}
ORDER = ["GHS01","GHS02","GHS03","GHS04","GHS05","GHS06","GHS07","GHS08","GHS09"]

# ---------- 픽토그램 트리거 집합 ----------
# 물리위험
GHS01_EXPLODING_BOMB: Set[str] = {"H200","H201","H202","H203","H204","H240","H241"}
GHS02_FLAME: Set[str] = {
    "H220","H221","H224","H225","H226","H228",  # 가스/액체/고체 인화성
    "H231","H232",                              # 발화성 가스
    "H250","H251","H252",                       # 자가발화/자가가열
    "H242","H261",                              # 자기반응성/물과 반응해 인화성 가스
}
GHS03_FLAME_OVER_CIRCLE: Set[str] = {"H270","H271","H272"}
GHS04_GAS_CYLINDER: Set[str] = {"H280","H281"}

# 건강위험 — 세부 경로 관리
ACUTE_ORAL_1_3: Set[str]  = {"H300","H301"}
ACUTE_DERM_1_3: Set[str]  = {"H310","H311"}
ACUTE_INHAL_1_3: Set[str] = {"H330","H331"}
ACUTE_ORAL_4: Set[str]    = {"H302"}
ACUTE_DERM_4: Set[str]    = {"H312"}
ACUTE_INHAL_4: Set[str]   = {"H332"}

# 부식/자극
CORROSIVE_SKIN_EYE: Set[str] = {"H314","H318"}  # 부식/심한 안손상
CORROSIVE_METAL: Set[str]    = {"H290"}         # 금속 부식 (자극 생략 규칙엔 사용 X)
IRRITATION_ONLY: Set[str]    = {"H315","H319"}  # 피부/눈 자극
SENSITIZATION_SKIN: Set[str] = {"H317"}         # 피부 과민
SENSITIZATION_RESP: Set[str] = {"H334"}         # 호흡 과민

# STOT / Aspiration
STOT_SEVERE: Set[str] = {"H370","H371","H372","H373"}  # SE1/2, RE1/2 -> GHS08
STOT_SE3: Set[str]    = {"H335","H336"}                # 단회노출 Cat.3 -> GHS07
ASPIRATION: Set[str]  = {"H304"}                       # 흡인유해 -> GHS08

# 환경
ENV_ACUTE_CHRONIC: Set[str] = {"H400","H410","H411"}    # 픽토그램 사용
ENV_CHRONIC3: Set[str] = {"H412"}                       # 보통 픽토그램 X (policy 옵션)

# 픽토그램별 기본 트리거 세트(라프)
BASE_TRIGGERS = {
    "GHS01": GHS01_EXPLODING_BOMB,
    "GHS02": GHS02_FLAME,
    "GHS03": GHS03_FLAME_OVER_CIRCLE,
    "GHS04": GHS04_GAS_CYLINDER,
    "GHS05": CORROSIVE_SKIN_EYE | CORROSIVE_METAL,
    "GHS06": ACUTE_ORAL_1_3 | ACUTE_DERM_1_3 | ACUTE_INHAL_1_3,
    "GHS07": IRRITATION_ONLY | SENSITIZATION_SKIN | STOT_SE3 | ACUTE_ORAL_4 | ACUTE_DERM_4 | ACUTE_INHAL_4,
    "GHS08": SENSITIZATION_RESP | STOT_SEVERE | ASPIRATION,
    "GHS09": ENV_ACUTE_CHRONIC,  # H412는 policy로 따로 처리
}

# ---------- 내부 유틸 ----------
def _norm_set(hcodes: Iterable[str]) -> Set[str]:
    return {h.strip().upper() for h in hcodes if isinstance(h, str) and h.strip()}

def _route_presence(hset: Set[str]) -> Dict[str, Dict[str, bool]]:
    """경로별 Cat1-3 / Cat4 존재 여부"""
    return {
        "oral":  {"cat13": bool(hset & ACUTE_ORAL_1_3),  "cat4": bool(hset & ACUTE_ORAL_4)},
        "derm":  {"cat13": bool(hset & ACUTE_DERM_1_3),  "cat4": bool(hset & ACUTE_DERM_4)},
        "inhal": {"cat13": bool(hset & ACUTE_INHAL_1_3), "cat4": bool(hset & ACUTE_INHAL_4)},
    }

# ---------- 메인 로직 ----------
def map_hcodes_to_pictos(hcodes: Iterable[str], policy: Dict[str, bool] | None = None) -> Dict[str, List[str]]:
    """
    policy:
      - include_env_h412: bool = False  # H412(Chronic 3)에도 GHS09 표시할지
    """
    policy = {"include_env_h412": False, **(policy or {})}
    hset = _norm_set(hcodes)

    pictos: Set[str] = set()

    # 1) 1차 포함 규칙
    if hset & GHS01_EXPLODING_BOMB:    pictos.add("GHS01")
    if hset & GHS02_FLAME:             pictos.add("GHS02")
    if hset & GHS03_FLAME_OVER_CIRCLE: pictos.add("GHS03")
    if hset & GHS04_GAS_CYLINDER:      pictos.add("GHS04")
    if hset & (CORROSIVE_SKIN_EYE | CORROSIVE_METAL): pictos.add("GHS05")
    if hset & BASE_TRIGGERS["GHS06"]:  pictos.add("GHS06")
    if hset & BASE_TRIGGERS["GHS07"]:  pictos.add("GHS07")
    if hset & BASE_TRIGGERS["GHS08"]:  pictos.add("GHS08")
    if (hset & ENV_ACUTE_CHRONIC) or (policy["include_env_h412"] and (hset & ENV_CHRONIC3)):
        pictos.add("GHS09")

    # 2) 우선순위/상쇄 규칙

    # 2-1) 경로별 급성독성 우선순위: 같은 경로에서 Cat1–3 존재 시 Cat4로 인한 GHS07은 제외
    if "GHS07" in pictos:
        route = _route_presence(hset)
        cat4_only = False
        # GHS07을 유지시킬 다른(비-급성독성4) 요인들?
        keep07_strong = bool(hset & (SENSITIZATION_SKIN | STOT_SE3 | IRRITATION_ONLY))
        if not keep07_strong:
            # 급성독성으로만 07이 생겼을 가능성이 낮지만 체크
            cat4_only = any(v["cat4"] for v in route.values())
        # 경로 충돌 판단
        same_route_suppressed = any(v["cat13"] and v["cat4"] for v in route.values())
        if cat4_only and same_route_suppressed:
            pictos.discard("GHS07")

    # 2-2) 부식성에 의한 자극 생략: Skin/Eye 부식(H314/H318) 있는 경우, H315/H319만으로 발생한 07은 제거
    if "GHS05" in pictos and "GHS07" in pictos:
        has_skin_eye_corr = bool(hset & CORROSIVE_SKIN_EYE)
        if has_skin_eye_corr:
            strong_keep = bool(hset & (SENSITIZATION_SKIN | STOT_SE3))  # H317/H335/H336
            irritation_present = bool(hset & IRRITATION_ONLY)
            if irritation_present and not strong_keep:
                pictos.discard("GHS07")

    # 정렬
    pic_list = [p for p in ORDER if p in pictos]
    labels = [PICTO_LABEL[p] for p in pic_list]
    return {"pictograms": pic_list, "labels": labels}

def map_hcodes_to_pictos_detailed(hcodes: Iterable[str], policy: Dict[str, bool] | None = None) -> List[Dict[str, List[str] | str]]:
    """
    상세 버전: 각 픽토그램에 대해 실제 트리거 H코드와 우선순위 메모를 함께 반환
    """
    base = map_hcodes_to_pictos(hcodes, policy=policy)
    picked = base["pictograms"]
    hset = _norm_set(hcodes)
    notes: List[str] = []

    # 우선순위 메모 생성
    route = _route_presence(hset)
    if "GHS07" not in picked and any(v["cat13"] and v["cat4"] for v in route.values()):
        notes.append("동일 경로에서 Cat.1–3 급성독성 존재로 Cat.4 기반 GHS07 생략")
    if ("GHS05" in picked) and ("GHS07" not in picked) and (hset & CORROSIVE_SKIN_EYE) and (hset & IRRITATION_ONLY):
        if not (hset & (SENSITIZATION_SKIN | STOT_SE3)):
            notes.append("피부/눈 부식성으로 자극(H315/H319) 기반 GHS07 생략")

    # 트리거 집합 계산
    TRIG = {
        "GHS01": GHS01_EXPLODING_BOMB,
        "GHS02": GHS02_FLAME,
        "GHS03": GHS03_FLAME_OVER_CIRCLE,
        "GHS04": GHS04_GAS_CYLINDER,
        "GHS05": (CORROSIVE_SKIN_EYE | CORROSIVE_METAL),
        "GHS06": BASE_TRIGGERS["GHS06"],
        "GHS07": BASE_TRIGGERS["GHS07"],
        "GHS08": BASE_TRIGGERS["GHS08"],
        "GHS09": (ENV_ACUTE_CHRONIC | (ENV_CHRONIC3 if (policy or {}).get("include_env_h412") else set())),
    }

    result = []
    for p in ORDER:
        if p not in picked:
            continue
        trig = sorted(t for t in hset if t in TRIG[p])
        result.append({
            "pictogram": p,
            "label": PICTO_LABEL[p],
            "triggers": trig,
            "rule_notes": notes if p == picked[-1] else [],
        })
    return result


# ---- quick self test ----
if __name__ == "__main__":
    tests = [
        # 인화 + 자극 => GHS02 + GHS07
        ["H225","H315","H319"],
        # 부식(피부/눈) => 자극으로 인한 07 생략
        ["H225","H314","H319"],
        # 경로별: 경구 Cat1–3 + 흡입 Cat4 → 다른 경로이므로 07 유지
        ["H301","H332"],
        # 동일 경로: 흡입 Cat1–3 + 흡입 Cat4 → Cat4로 인한 07 생략
        ["H331","H332"],
        # 과민/자극/중추억제 혼합
        ["H317","H335","H336"],
        # STOT/CMR/흡인/환경
        ["H304","H350","H410"],
        # 산화 + 인화
        ["H270","H225"],
        # 고압가스
        ["H280"],
        # H412 정책 적용 전/후
        ["H412"],
    ]
    for i, hs in enumerate(tests, 1):
        r = map_hcodes_to_pictos_detailed(hs, policy={"include_env_h412": True})
        print(f"[case{i}] {hs} -> {[x['pictogram'] for x in r]} | {r}")
