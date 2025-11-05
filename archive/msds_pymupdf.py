
# streamlit_msds_app.py
import re
import io
import streamlit as st
import fitz  # PyMuPDF
import pandas as pd

st.set_page_config(page_title="MSDS Extractor (Streamlit)", layout="wide")
st.title("MSDS Uploader & Extractor")
st.caption("Upload an MSDS PDF. This demo extracts H/P codes, CAS numbers, and component rows heuristically.")

CAS_RE = r"\b(\d{2,7}-\d{2}-\d)\b"
H_RE = r"\bH\d{3}[A-Z]?\b"
P_RE = r"\bP\d{3}[A-Z]?(?:\+P\d{3}[A-Z]?)?\b"

def read_pdf_text(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    chunks = []
    for i in range(len(doc)):
        page = doc[i]
        # get_text() keeps a loose layout which is usually fine for regex-based parsing
        chunks.append(page.get_text())
    return "\n".join(chunks)

def guess_product_name(text: str) -> str | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # Simple heuristics looking at the first ~100 lines
    for ln in lines[:100]:
        for pat in [r"제품명[:\s]+(.{2,60})", r"Product Name[:\s]+(.{2,60})", r"식별자[:\s]+(.{2,60})"]:
            m = re.search(pat, ln, flags=re.I)
            if m:
                return m.group(1).strip()
    # fallback to first non-empty line
    return lines[0] if lines else None

def extract_components(text: str):
    rows = []
    for ln in text.splitlines():
        m_cas = re.search(CAS_RE, ln)
        if not m_cas:
            continue
        cas = m_cas.group(1)
        conc_m = re.search(r"(\d{1,3}(?:\.\d+)?\s*%|\d+\s*ppm|\d+\s*mg/m\^?3)", ln, flags=re.I)
        name = re.sub(CAS_RE, "", ln).strip(" -:\t")
        rows.append(
            {
                "name": re.sub(r"\s{2,}", " ", name),
                "cas": cas,
                "concentration": conc_m.group(1) if conc_m else ""
            }
        )
    # deduplicate by CAS, keep first seen
    seen = set()
    uniq = []
    for r in rows:
        if r["cas"] in seen:
            continue
        seen.add(r["cas"])
        uniq.append(r)
    return uniq

st.subheader("1) 파일 업로드")
file = st.file_uploader("MSDS PDF 업로드", type=["pdf"])

if file:
    file_bytes = file.read()
    with st.spinner("텍스트 추출 중..."):
        text = read_pdf_text(file_bytes)

    st.subheader("2) 원문 미리보기")
    st.text_area("첫 15000자 프리뷰", text[:15000], height=1000)

    st.subheader("3) 필드 추출 결과")
    product_name = guess_product_name(text)
    H = sorted(set(re.findall(H_RE, text)))
    P = sorted(set(re.findall(P_RE, text)))
    cas_all = sorted(set(re.findall(CAS_RE, text)))

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("H codes", len(H))
    with col2:
        st.metric("P codes", len(P))
    with col3:
        st.metric("Unique CAS", len(cas_all))

    st.write("제품명 추정:", product_name or "-")
    st.write("대표 CAS:", cas_all[0] if cas_all else "-")

    st.write("H codes:", ", ".join(H) if H else "-")
    st.write("P codes:", ", ".join(P) if P else "-")

    st.subheader("4) 성분표")
    components = extract_components(text)
    if components:
        st.dataframe(pd.DataFrame(components))
    else:
        st.info("성분표 후보 라인을 찾지 못했습니다. 표 구조가 복잡하거나 스캔본일 수 있습니다.")

    st.subheader("5) JSON 내보내기")
    payload = {
        "product_name": product_name,
        "hazards": {"H": H, "P": P},
        "components": components,
        "all_cas": cas_all,
    }
    st.download_button(
        "Download JSON",
        data=pd.Series(payload).to_json(),
        file_name="msds_extract.json",
        mime="application/json",
    )

    st.caption("스캔 PDF인 경우에는 OCR 단계(Tesseract/PaddleOCR)를 추가해야 합니다. 이 데모는 텍스트 레이어가 존재하는 PDF에 최적화되어 있습니다.")
