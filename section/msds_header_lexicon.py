# msds_header_lexicon.py
# GHS 16개 섹션 캐논키와 기본 동의어/변형 리스트(한/영/혼용)
# 필요 시 config/synonyms.yml 로 덮어씌웁니다.

GHS_TERMS = {
    "identification":       {"ko": "화학제품과 회사에 관한 정보", "en": "Identification"},
    "hazards":              {"ko": "유해성ㆍ위험성",              "en": "Hazard Identification"},
    "composition":          {"ko": "구성성분의 명칭 및 함유량",    "en": "Composition/Information on Ingredients"},
    "first_aid":            {"ko": "응급조치 요령",                "en": "First-aid Measures"},
    "fire_fighting":        {"ko": "폭발ㆍ화재 시 대처방법",        "en": "Fire-fighting Measures"},
    "accidental_release":   {"ko": "누출사고 시 대처방법",          "en": "Accidental Release Measures"},
    "handling_storage":     {"ko": "취급 및 저장방법",              "en": "Handling and Storage"},
    "exposure_ppe":         {"ko": "노출방지 및 개인보호구",        "en": "Exposure Controls/Personal Protection"},
    "physical_chemical":    {"ko": "물리화학적 특성",              "en": "Physical and Chemical Properties"},
    "stability_reactivity": {"ko": "안정성 및 반응성",             "en": "Stability and Reactivity"},
    "toxicology":           {"ko": "독성에 관한 정보",             "en": "Toxicological Information"},
    "ecology":              {"ko": "환경에 미치는 영향",           "en": "Ecological Information"},
    "disposal":             {"ko": "폐기 시 주의사항",             "en": "Disposal Considerations"},
    "transport":            {"ko": "운송에 필요한 정보",           "en": "Transport Information"},
    "regulation":           {"ko": "법규에 관한 정보", "en": "Regulatory Information"},
    "other":                {"ko": "그 밖의 참고사항", "en": "Other Information"},  #
}

# 캐논키별 기본 동의어(벤더/KOSHA/해외 템플릿에서 자주 보이는 변형)
BASE_SYNONYMS = {
    "identification": [
        "화학제품과 회사에 관한 정보", "화학제품과 제조사 정보", "제품 정보", "물질 정보", "제품명", "공급자 정보",
        "식별", "식별자", "Identification", "Product identification", "Supplier information",
    ],
    "hazards": [
        "유해성 위험성", "유해·위험성", "경고표지", "표지요소", "위험성", "주의표시",
        "Hazard", "Hazard identification", "Label elements",
    ],
    "composition": [
        "구성성분의 명칭 및 함유량", "성분표", "성분 정보", "조성 정보",
        "Composition", "Ingredients", "Information on ingredients",
    ],
    "first_aid": [
        "응급조치", "응급조치 요령", "응급 처치",
        "First-aid", "First aid measures",
    ],
    "fire_fighting": [
        "폭발 화재 시 대처방법", "화재시 대처방법", "소화", "소화조치",
        "Fire-fighting", "Fire fighting measures",
    ],
    "accidental_release": [
        "누출사고 시 대처방법", "누출 대처", "유출 대처",
        "Accidental release", "Spillage response",
    ],
    "handling_storage": [
        "취급 및 저장방법", "취급 및 저장", "저장 방법",
        "Handling and storage",
    ],
    "exposure_ppe": [
        "노출방지 및 개인보호구", "노출기준", "보호구", "개인보호",
        "Exposure controls", "Personal protection", "PPE",
    ],
    "physical_chemical": [
        "물리화학적 특성", "물리적 화학적 특성",
        "Physical and chemical properties",
    ],
    "stability_reactivity": [
        "안정성 및 반응성", "반응성", "안정성",
        "Stability and reactivity",
    ],
    "toxicology": [
        "독성에 관한 정보", "독성 정보",
        "Toxicological information",
    ],
    "ecology": [
        "환경에 미치는 영향", "생태 영향", "생태독성",
        "Ecological information",
    ],
    "disposal": [
        "폐기 시 주의사항", "폐기", "폐기 방법",
        "Disposal considerations",
    ],
    "transport": [
        "운송에 필요한 정보", "운송 정보",
        "Transport information",
    ],
    "regulation": [
        "법규에 관한 정보", "규제 정보", "법규/규제",
        "Regulatory information",
    ],
    "other": [
        "그 밖의 참고사항",  
        "기타 참고자료",    
        "기타",
        "Other information",
        "Miscellaneous",
    ],
}
