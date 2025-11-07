# -*- coding: utf-8 -*-
"""
GHS 16개 섹션 캐논키와 동의어(한국어/영문 혼합).
다른 업체 포맷을 흡수하기 위한 '제목 키워드 뭉치'만 모아둔 파일.
"""

from __future__ import annotations
from typing import Dict, List

# Canon keys (영문 키 → 번호)
CANON_TO_NUM = {
    "identification": "1",
    "hazards": "2",
    "composition": "3",
    "first_aid": "4",
    "fire_fighting": "5",
    "accidental_release": "6",
    "handling_storage": "7",
    "exposure_ppe": "8",
    "physical_chemical": "9",
    "stability_reactivity": "10",
    "toxicology": "11",
    "ecology": "12",
    "disposal": "13",
    "transport": "14",
    "regulation": "15",
    "other": "16",
}

# 번호 → 캐논키
NUM_TO_CANON = {v: k for k, v in CANON_TO_NUM.items()}

# 표준 표시(참고용)
GHS_TERMS: Dict[str, Dict[str, str]] = {
    "1":  {"ko": "제품 및 회사의 식별", "en": "Identification"},
    "2":  {"ko": "유해·위험성", "en": "Hazard(s) identification"},
    "3":  {"ko": "구성성분의 명칭 및 함유량", "en": "Composition/Information on ingredients"},
    "4":  {"ko": "응급조치", "en": "First-aid measures"},
    "5":  {"ko": "화재 시 조치", "en": "Fire-fighting measures"},
    "6":  {"ko": "누출사고 시 조치", "en": "Accidental release measures"},
    "7":  {"ko": "취급 및 저장", "en": "Handling and storage"},
    "8":  {"ko": "노출방지 및 개인보호구", "en": "Exposure controls/Personal protection"},
    "9":  {"ko": "물리·화학적 특성", "en": "Physical and chemical properties"},
    "10": {"ko": "안정성 및 반응성", "en": "Stability and reactivity"},
    "11": {"ko": "독성에 관한 정보", "en": "Toxicological information"},
    "12": {"ko": "환경에 미치는 영향", "en": "Ecological information"},
    "13": {"ko": "폐기 시 주의사항", "en": "Disposal considerations"},
    "14": {"ko": "운송에 필요한 정보", "en": "Transport information"},
    "15": {"ko": "법적 규제 현황", "en": "Regulatory information"},
    "16": {"ko": "기타 참고사항", "en": "Other information"},
}

# 섹션 제목 동의어/키워드 꾸러미
# (짧은 명사/구 위주, “라벨:값” 본문 단어는 포함하지 않음)
BASE_SYNONYMS: Dict[str, List[str]] = {
    "identification": [
        "제품 및 회사", "화학제품과 제조회사", "제품 식별", "식별", "제품명", "제품 식별자",
        "supplier identification", "company identification", "identification"
    ],
    "hazards": [
        "유해성", "위험성", "경고문구", "주의문구", "그림문자", "신호어", "표시사항",
        "hazards", "hazard identification", "label elements", "signal word"
    ],
    "composition": [
        "구성성분", "성분", "조성", "원료 정보", "혼합물 정보",
        "composition", "ingredients", "mixture"
    ],
    "first_aid": [
        "응급조치", "응급 처치", "의학적 조치", "흡입 시", "피부 접촉 시", "눈 접촉 시", "삼킨 경우",
        "first-aid", "first aid"
    ],
    "fire_fighting": [
        "화재 시 조치", "소화", "소화 방법", "적용 소화제", "부적합 소화제",
        "fire-fighting", "fire fighting", "fire measures"
    ],
    "accidental_release": [
        "누출사고", "유출사고", "누출 시 조치", "비상 조치",
        "accidental release", "spillage", "leak", "spill"
    ],
    "handling_storage": [
        "취급 및 저장", "취급", "저장", "보관", "handling", "storage", "store"
    ],
    "exposure_ppe": [
        "노출기준", "개인보호구", "보호장비", "작업장 관리", "환기", "PPE",
        "exposure control", "personal protection", "protective equipment"
    ],
    "physical_chemical": [
        "물리·화학적 특성", "물리화학적 성질", "물리적 성질", "물리화학적 특성",
        "physical and chemical properties", "properties"
    ],
    "stability_reactivity": [
        "안정성", "반응성", "위해반응", "회피조건", "금지물질",
        "stability", "reactivity"
    ],
    "toxicology": [
        "독성", "독성 정보", "급성독성", "장기독성", "발암성", "생식독성",
        "toxicology", "toxicological information"
    ],
    "ecology": [
        "생태", "환경 영향", "수생태 독성", "지속성", "분해성", "생물농축",
        "ecology", "ecological information"
    ],
    "disposal": [
        "폐기", "폐기 시 주의사항", "폐기방법", "폐기상 주의",
        "disposal", "disposal considerations"
    ],
    "transport": [
        "운송", "운송 정보", "UN 번호", "포장그룹", "해사규정", "항공운송",
        "transport", "transport information"
    ],
    "regulation": [
        "규제", "법규", "법적 규제", "관련 법령", "화관법", "화평법", "산안법",
        "regulatory", "regulatory information"
    ],
    "other": [
        "기타", "참고", "기타 참고사항", "개정 이력", "비고",
        "other", "references", "revision", "note"
    ],
}
