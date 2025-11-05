# 고정(DPI=300, lang=kor+eng). 옵션 UI 없음.
# 흐름: 업로드 → 텍스트 확보(디지털/스캔 자동) → 미리보기 → H/P/CAS → 섹션 분리 → SHMS 매핑 → 하단 로그

import re
import streamlit as st
import pandas as pd

from msds_text_extractor import extract_pdf_text_auto
from section.msds_section_splitter import split_sections_auto
from field.shms_mapper import map_to_shms

# 기본 패턴용 정규식
CAS_RE = r"\b(\d{2,7}-\d{2}-\d)\b"
H_RE   = r"\bH\d{3}[A-Z]?\b"
P_RE   = r"\bP\d{3}[A-Z]?(?:\+P\d{3}[A-Z]?)?\b"

st.set_page_config(page_title="MSDS Extractor", layout="wide")
st.title("MSDS Uploader & Extractor")
st.caption("PDF → Text/OCR(auto) → Section Split → SHMS Mapping. DPI=300, lang=kor+eng")

def extract_basic_fields(text: str):
    """문서 전체에서 H/P/CAS 기본 패턴만 추출"""
    H   = sorted(set(re.findall(H_RE, text)))
    P   = sorted(set(re.findall(P_RE, text)))
    CAS = sorted(set(re.findall(CAS_RE, text)))
    return H, P, CAS

file = st.file_uploader("MSDS PDF 업로드 / Upload PDF", type=["pdf"])

if file is not None:
    file_bytes: bytes = file.read()

    # 1) 텍스트 확보(디지털/스캔 자동판별 + OCR 재시도 포함)
    res = extract_pdf_text_auto(
        file_bytes=file_bytes,
        dpi=300,
        lang="kor+eng",
        tessdata_dir=None,
    )
    text = res.merged_text

    # 2) 미리보기
    st.subheader("원문 미리보기 / Text Preview")
    st.text_area("앞 10,000자 / First 10,000 chars", text[:10000], height=350)

    # 3) 기본 패턴 추출
    H, P, CAS = extract_basic_fields(text)
    c1, c2, c3 = st.columns(3)

    # 4) 섹션 분리 (섹션 본문 자동 높이: markdown 코드블록 사용)
    st.subheader("섹션 분리 / Section Split")
    sections, sec_logs, template = split_sections_auto(text)

    # 섹션 미리보기(실제 문서에서 추출된 제목을 사용)
    if sections:
        # 표로 추출 소제목/길이/프리뷰 먼저 보여주기
        rows = []
        for key, sec in sections.items():
            title = sec.get("title") or key
            body = sec.get("text", "")
            rows.append((title, len(body), body[:150].replace("\n", " ")))
        df = pd.DataFrame(rows, columns=["추출 소제목", "길이", "미리보기"])
        st.dataframe(df, width='stretch', hide_index=True)

        # 본문은 자동 높이: text_area 대신 markdown 코드블록
        with st.expander("섹션 본문 펼치기 / Expand Full Sections", expanded=False):
            for key, sec in sections.items():
                title = sec.get("title") or key
                body  = sec.get("text", "")
                st.markdown(f"### {title}")
                # 코드블록으로 자동 확장 + 개행/공백 보존
                st.markdown(f"```text\n{body}\n```")
    else:
        st.info("섹션 헤더를 찾지 못했습니다.")
    
    # 5) SHMS 매핑
    st.subheader("SHMS 매핑 결과 / SHMS Mapping (통합)")
    mapped = map_to_shms(text, sections)

    col1, col2 = st.columns(2)
    with col1:
        st.caption("기본정보")
        st.json(mapped["basic"])
        st.caption("사업장/사용")
        st.json(mapped["site_usage"])
        st.caption("연락처")
        st.json(mapped["contacts"])
        st.caption("보관·취급")
        st.json(mapped["storage"])
    with col2:
        st.caption("GHS 핵심")
        st.json(mapped["ghs_detail"])
        st.caption("물리·화학적 특성 (섹션 9)")
        st.json(mapped["physchem"])
        st.caption("노출 기준(메모)")
        st.json(mapped["exposure"])

    st.subheader("구성성분 / Composition")
    st.dataframe(pd.DataFrame(mapped["composition"]), width='stretch', hide_index=True)

    st.subheader("법적규제사항 / Legal Regulations")
    st.dataframe(pd.DataFrame(mapped["legal_regulations"]), width='stretch', hide_index=True)

    # 6) 처리 로그(맨 아래에 전체 표시)
    st.subheader("처리 로그 / Processing Log")
    page_summaries = []
    for p in res.pages:
        if p.source == "digital":
            page_summaries.append(f"[p{p.page_index+1}] 디지털 사용.")
        elif p.source == "ocr":
            page_summaries.append(f"[p{p.page_index+1}] 스캔 추정 → OCR.")
        else:
            page_summaries.append(f"[p{p.page_index+1}] 디지털+OCR 병합.")
    all_logs = []
    all_logs.extend(res.final_decision_log)
    all_logs.append(" | ".join(page_summaries))
    all_logs.extend(sec_logs)
    all_logs.extend(mapped.get("_log", []))
    all_logs.extend(mapped["_log"])
    st.subheader("처리 로그 / Processing Log")
    st.code("\n".join(all_logs), language="text")

else:
    st.info("PDF를 업로드하세요 / Please upload a PDF.")
