# streamlit_msds_app.py
# PDF → Text/OCR(auto) → Visual-Order Normalize → Section Split
# → 섹션2(H/P 전체, 분류표) → 섹션3(구성성분; 부등호/범위/단위 파싱)
# → 섹션9(물리·화학) → 섹션15(규제항목)
# → GHS 그림문자(GIF) & 트리거 H코드
# 파일별 결과 + 전체 집계/CSV 다운로드

import os
import re
import io
import tempfile
import streamlit as st
import pandas as pd

# ---- 프로젝트 모듈
from msds_text_extractor import extract_pdf_text_auto
try:
    from utils.robust_pdf_text import extract_pdf_text_visual_order
    _HAS_VISUAL = True
except Exception:
    _HAS_VISUAL = False

from section.msds_section_splitter import split_sections_auto
from field.legal_reg_table import build_legal_table
from field.hazard_class_table import build_hazard_class_table
from field.physchem_extractor import extract_physchem
from field.ghs_pictogram_mapper import map_hcodes_to_pictos_detailed
from field.hp_simple import extract_hp_simple

# (있으면) 고급 구성성분 파서 폴백
try:
    from field.composition_extractor import extract_composition as _fallback_comp_extractor
    _HAS_COMP_FALLBACK = True
except Exception:
    _HAS_COMP_FALLBACK = False

# ---- 패턴
CAS_RE = r"\b(\d{2,7}-\d{2}-\d)\b"
H_RE   = r"\bH\d{3}[A-Z]?\b"
P_RE   = r"\bP\d{3}[A-Z]?(?:\+P\d{3}[A-Z]?)?\b"
MSDS_NO_RE = r"\b(?:MSDS|SDS)\s*(?:No\.?|번호|#)\s*[:：]?\s*([A-Za-z0-9\-\._]+)"

# ---- 이미지 폴더(프로젝트 상대경로)
IMAGE_DIR = os.path.join("msds", "image")  # 예: msds/image/GHS01.gif

st.set_page_config(page_title="MSDS Batch Extractor", layout="wide")
st.title("MSDS Batch Uploader & Extractor")
st.caption("여러 PDF를 한 번에 올려 섹션2/3/9/15, GHS 그림문자, H/P 라인, 메타(제품명·회사·MSDS No·CAS)까지 일괄 추출")

# ------------------ 유틸 ------------------
def extract_basic_fields(text: str):
    H   = sorted(set(re.findall(H_RE, text)))
    P   = sorted(set(re.findall(P_RE, text)))
    CAS = sorted(set(re.findall(CAS_RE, text)))
    return H, P, CAS

_MSDS_ANCHORS = [
    "제품 및 회사 식별","유해성","위험성","구성성분","응급조치","폭발","화재","누출사고",
    "취급 및 저장","노출방지 및 개인보호구","물리화학적 특성","안정성 및 반응성","독성",
    "환경에 미치는 영향","폐기","운송","법적 규제","규제 정보","기타 참고사항",
    "identification","hazards","composition","first-aid","firefighting","accidental release",
    "handling and storage","exposure controls","physical","stability and reactivity","toxicological",
    "ecological","disposal","transport","regulatory","other information",
]

def _score_headers(t: str) -> int:
    if not t: return -1
    low = t.lower()
    return sum(1 for k in _MSDS_ANCHORS if k.lower() in low)

def _jaccard(a: str, b: str) -> float:
    def trigrams(s):
        s = re.sub(r"\s+", " ", s.strip())
        return {s[i:i+3] for i in range(max(0, len(s)-2))}
    if not a or not b: return 0.0
    A, B = trigrams(a[:20000]), trigrams(b[:20000])
    if not A or not B: return 0.0
    inter = len(A & B); union = len(A | B)
    return inter/union if union else 0.0

def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    return buf.getvalue().encode("utf-8-sig")

def _auto_height(s: str) -> int:
    if not s: return 140
    n_lines = s.count("\n") + 1
    by_lines = 22 * min(35, n_lines)
    by_chars = int(min(900, max(140, len(s) * 0.04)))
    return max(140, min(900, max(by_lines, by_chars)))

def _first_nonempty(*vals):
    for v in vals:
        if v and str(v).strip():
            return v
    return ""

# ------------------ 메타 추출 ------------------
def _sec_text(sections: dict, keys=('physical_chemical', 'composition', 'identification')):
    return {k: sections.get(k, {}).get("text", "") for k in keys}

def extract_meta(text: str, sections: dict) -> dict:
    sec = _sec_text(sections, keys=('identification','composition'))
    ident = sec.get('identification', "") or ""
    comp  = sec.get('composition', "") or ""

    product = (
        _search_label_value(ident, ["제품명","제품 식별자","표지명","Product name","Product identifier","Trade name"]) or
        _search_label_value(text,  ["제품명","제품 식별자","Product name","Product identifier","Trade name"])
    )

    supplier = (
        _search_label_value(ident, ["제조사","회사명","공급사","수입사","Manufacturer","Supplier","Company name","Importer"]) or
        _search_label_value(text,  ["제조사","회사명","공급사","Supplier","Manufacturer","Company"])
    )

    msds_no = (
        _search_regex_group(ident, MSDS_NO_RE) or
        _search_regex_group(text,  MSDS_NO_RE)
    )

    cas_all = re.findall(CAS_RE, comp) or re.findall(CAS_RE, text)
    rep_cas = cas_all[0] if cas_all else ""

    return {
        "product_name": (product or "").strip(),
        "supplier": (supplier or "").strip(),
        "msds_no": (msds_no or "").strip(),
        "representative_cas": rep_cas
    }

def _search_label_value(block: str, labels: list) -> str:
    if not block: return ""
    for lb in labels:
        m = re.search(rf"{re.escape(lb)}\s*[:：]\s*(.+)", block, re.I)
        if m:
            return m.group(1).strip()
    for lb in labels:
        for line in block.splitlines():
            if re.search(rf"\b{re.escape(lb)}\b", line, re.I):
                parts = re.split(r"\s{2,}", line.strip())
                if len(parts) >= 2:
                    return parts[-1].strip()
    return ""

def _search_regex_group(block: str, pattern: str) -> str:
    if not block: return ""
    m = re.search(pattern, block, re.I)
    return m.group(1).strip() if m else ""

# ------------------ 구성성분(섹션3) 파서 ------------------
# 헤더/셀 분해 보조
_NAME_TOKENS = ["성분", "명칭", "물질명", "화학명", "name", "component", "substance"]
_CAS_TOKENS  = ["cas", "cas no", "cas번호", "cas no.", "cas number"]
_CONC_TOKENS = ["함유량", "농도", "함량", "비율", "concentration", "content", "wt%", "%", "range"]
_EC_TOKENS   = ["einecs", "ec", "등록번호", "registration"]

def _split_cells(line: str) -> list:
    line = line.strip().strip("|")
    if "|" in line:
        cells = [c.strip() for c in line.split("|")]
    else:
        cells = re.split(r"\s{2,}|\t+", line)
        cells = [c.strip() for c in cells if c.strip()]
    return cells

def _is_header_like(line: str) -> bool:
    low = line.lower()
    score = sum(tok in low for tok in ["cas", "농도", "함유", "concentration", "성분", "name", "ec", "등록"])
    return score >= 2

def _classify_columns(cells: list) -> dict:
    def score(cell: str, toks: list) -> int:
        l = cell.lower()
        return sum(1 for t in toks if t in l)
    best = {"name": None, "cas": None, "conc": None, "ec": None}
    for i, c in enumerate(cells):
        s_name = score(c, _NAME_TOKENS)
        s_cas  = score(c, _CAS_TOKENS)
        s_conc = score(c, _CONC_TOKENS)
        s_ec   = score(c, _EC_TOKENS)
        if s_name and (best["name"] is None): best["name"] = i
        if s_cas  and (best["cas"]  is None): best["cas"]  = i
        if s_conc and (best["conc"] is None): best["conc"] = i
        if s_ec   and (best["ec"]   is None): best["ec"]   = i
    return best

def _clean_name(s: str) -> str:
    s = s.strip(" -:\t|·•")
    s = re.sub(r"\s{2,}", " ", s)
    return s

# 농도 파싱(부등호/범위/단위)
# === 기존 정의를 전부 교체 ===
_CONC_UNIT = r"(?:wt/?%|w/?w%|vol/?%|v/?v%|%|ppm|mg/?m\^?3|mg/?L|g/?L|µg/?L|ug/?L|mg/?kg|g/?kg)"
_CONC_VAL  = r"(?:\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d{1,4}(?:\.\d+)?)"

# 각 대안마다 고유 그룹명 사용
_CONC_RANGE  = rf"(?P<low>{_CONC_VAL})\s*(?:[-–~∼]\s*|to\s+)(?P<high>{_CONC_VAL})\s*(?P<unit_r>{_CONC_UNIT})?"
_CONC_CMP    = rf"(?P<cmp><=|>=|<|>|≤|≥)\s*(?P<val_c>{_CONC_VAL})\s*(?P<unit_c>{_CONC_UNIT})?"
_CONC_SINGLE = rf"(?P<val_s>{_CONC_VAL})\s*(?P<unit_s>{_CONC_UNIT})?"

_CONC_RE = re.compile(rf"(?:{_CONC_RANGE}|{_CONC_CMP}|{_CONC_SINGLE})", re.I)

def _clean_num(s: str):
    try:
        return float(s.replace(",", ""))
    except Exception:
        return s

def parse_conc(raw: str) -> dict:
    raw = (raw or "").strip()
    m = _CONC_RE.search(raw)
    if not m:
        return {"raw": raw}

    gd = m.groupdict()
    # unit 통합
    unit = gd.get("unit_r") or gd.get("unit_c") or gd.get("unit_s") or ""
    unit = unit.replace(" ", "") if unit else ""

    out = {"raw": raw}
    if unit:
        out["unit"] = unit

    if gd.get("low") and gd.get("high"):
        out["low"]  = _clean_num(gd["low"])
        out["high"] = _clean_num(gd["high"])
    elif gd.get("cmp") and gd.get("val_c"):
        out["cmp"]   = "≤" if gd["cmp"] in ("<=", "≤") else "≥" if gd["cmp"] in (">=", "≥") else gd["cmp"]
        out["value"] = _clean_num(gd["val_c"])
    elif gd.get("val_s"):
        out["value"] = _clean_num(gd["val_s"])

    return out

def _format_conc_display(c: dict) -> str:
    if not c: return ""
    unit = c.get("unit", "")
    if ("low" in c) or ("high" in c):
        lo = c.get("low",""); hi = c.get("high","")
        core = f"{lo} ~ {hi}".strip(" ~")
        return f"{core} {unit}".strip()
    if "value" in c:
        core = f"{c.get('value')}"
        if "cmp" in c: core = f"{c['cmp']} {core}"
        return f"{core} {unit}".strip()
    return c.get("raw","")

def _find_conc(s: str) -> str:
    m = _CONC_RE.search(s)
    return m.group(0).strip() if m else ""

def extract_composition_table(text: str, sections: dict) -> pd.DataFrame:
    sec_comp = (sections.get("composition", {}) or {}).get("text", "") or text
    lines = [ln.rstrip() for ln in sec_comp.splitlines() if ln.strip()]

    rows = []
    # 1) 표 헤더 감지 → 열 기준 파싱
    header_idx, colmap = -1, None
    for i, ln in enumerate(lines[:40]):
        if _is_header_like(ln):
            cells = _split_cells(ln)
            if len(cells) >= 2:
                colmap = _classify_columns(cells)
                if colmap.get("cas") is not None:
                    header_idx = i
                    break

    if colmap and colmap.get("cas") is not None:
        for ln in lines[header_idx+1:]:
            cells = _split_cells(ln)
            if not cells: continue
            ci = colmap["cas"]
            joined = " | ".join(cells)
            m = re.search(CAS_RE, cells[ci] if ci < len(cells) else joined) or re.search(CAS_RE, joined)
            if not m: 
                continue
            cas = m.group(1)

            # 이름
            name = ""
            ni = colmap.get("name")
            if ni is not None and ni < len(cells):
                name = _clean_name(cells[ni])
            if not name:
                for j in (ci-1, ci+1):
                    if 0 <= j < len(cells):
                        nm = _clean_name(cells[j])
                        if nm:
                            name = nm; break

            # 농도
            conc_raw = ""
            ci2 = colmap.get("conc")
            if ci2 is not None and ci2 < len(cells):
                conc_raw = cells[ci2]
            if not conc_raw:
                conc_raw = _find_conc(joined) or ""
            conc_parsed = parse_conc(conc_raw)
            conc_disp   = _format_conc_display(conc_parsed)

            # EC
            ec = ""
            ei = colmap.get("ec")
            if ei is not None and ei < len(cells):
                ec = cells[ei]

            rows.append({
                "name": name, "cas": cas,
                "concentration": conc_disp,
                "conc_unit": conc_parsed.get("unit",""),
                "conc_low": conc_parsed.get("low",""),
                "conc_high": conc_parsed.get("high",""),
                "conc_value": conc_parsed.get("value",""),
                "conc_cmp": conc_parsed.get("cmp",""),
                "conc_raw": conc_parsed.get("raw",""),
                "ec_no": ec
            })

    # 2) 라인형 폴백
    if not rows:
        for ln in lines:
            m = re.search(CAS_RE, ln)
            if not m: 
                continue
            cas = m.group(1)
            left = ln[:m.start()].strip()
            right = ln[m.end():].strip()
            if re.search(r"\b(cas(\s*hs)?|cas\s*no\.?|cas\s*번호)\b", left, re.I):
                name = _clean_name(right)
            else:
                name = _clean_name(left) or _clean_name(right)
            conc_parsed = parse_conc(ln)
            conc_disp   = _format_conc_display(conc_parsed)
            rows.append({
                "name": name, "cas": cas,
                "concentration": conc_disp,
                "conc_unit": conc_parsed.get("unit",""),
                "conc_low": conc_parsed.get("low",""),
                "conc_high": conc_parsed.get("high",""),
                "conc_value": conc_parsed.get("value",""),
                "conc_cmp": conc_parsed.get("cmp",""),
                "conc_raw": conc_parsed.get("raw",""),
                "ec_no": ""
            })

    # 3) 후처리
    if rows:
        cleaned, seen = [], set()
        for r in rows:
            key = (r["cas"], r.get("name","").lower(), r.get("conc_raw","").lower())
            if key in seen: 
                continue
            seen.add(key); cleaned.append(r)
        cols = ["name","cas","concentration","conc_unit","conc_low","conc_high","conc_value","conc_cmp","conc_raw","ec_no"]
        return pd.DataFrame(cleaned, columns=cols)

    # 4) 외부 폴백(있으면)
    if _HAS_COMP_FALLBACK:
        try:
            comp_rows, _, _ = _fallback_comp_extractor(
                text=text, comp_section_text=sections.get("composition", {}).get("text", "")
            )
            return pd.DataFrame(comp_rows) if comp_rows else pd.DataFrame(columns=["name","cas","concentration","ec_no"])
        except Exception:
            pass

    return pd.DataFrame(columns=["name","cas","concentration","ec_no"])

# ------------------ 멀티 업로더 ------------------
files = st.file_uploader("MSDS PDF 다중 업로드", type=["pdf"], accept_multiple_files=True)
if not files:
    st.info("PDF 여러 개를 선택해 업로드하세요.")
    st.stop()

# 누적 저장소
summary_rows, agg_hazard, agg_legal = [], [], []
agg_phys, agg_hp_lines, agg_comp, agg_meta = [], [], [], []

progress = st.progress(0)
status = st.empty()

for idx, file in enumerate(files, start=1):
    status.write(f"[{idx}/{len(files)}] 처리 중: {file.name}")

    # 임시 저장
    tmp_dir = tempfile.mkdtemp(prefix="msds_")
    pdf_path = os.path.join(tmp_dir, file.name)
    with open(pdf_path, "wb") as f:
        f.write(file.getbuffer())

    # 텍스트 추출
    res = extract_pdf_text_auto(
        file_bytes=open(pdf_path, "rb").read(),
        dpi=300, lang="kor+eng", tessdata_dir=None,
    )
    text_auto = (getattr(res, "merged_text", None) or "").strip()

    # 시각 순서 보정
    text_visual, visual_err = "", None
    if _HAS_VISUAL:
        try:
            text_visual = extract_pdf_text_visual_order(pdf_path) or ""
        except Exception as e:
            visual_err = f"visual-order 실패: {e}"

    # 선택 휴리스틱
    score_auto   = _score_headers(text_auto)
    score_visual = _score_headers(text_visual) if text_visual else -1
    len_auto     = len(text_auto)
    len_visual   = len(text_visual)
    overlap      = _jaccard(text_visual, text_auto) if (text_visual and text_auto) else 0.0

    use_visual = False
    if text_visual:
        cond_len   = (len_visual >= max(400, 0.9 * len_auto))
        cond_head  = (score_visual >= score_auto)
        cond_head2 = (score_visual >= score_auto + 2)
        cond_diff  = (overlap <= 0.4 and (len_visual > len_auto*0.85) and score_visual >= score_auto)
        use_visual = (cond_len and cond_head) or cond_head2 or cond_diff

    text_src = "visual" if (use_visual and text_visual) else "auto"
    text = text_visual if (text_src == "visual") else text_auto

    # 기본 패턴
    H, P, CAS = extract_basic_fields(text)

    # 섹션 분리
    sections, sec_logs, template = split_sections_auto(text)

    # 섹션2: H/P 원문 라인
    hp_simple = extract_hp_simple(text, sections)

    # 섹션2: 분류/구분 표
    hz_df = pd.DataFrame()
    try:
        hz_rows = build_hazard_class_table(text)
        hz_df = pd.DataFrame(hz_rows)
        if not hz_df.empty:
            hz_df["file"] = file.name
            agg_hazard.append(hz_df)
    except Exception:
        pass

    # 섹션3: 구성성분 표
    comp_df = extract_composition_table(text, sections)
    if not comp_df.empty:
        comp_df["file"] = file.name
        agg_comp.append(comp_df)

    # 섹션9: 물리·화학 (섹션9 우선, 없으면 전역)
    sec9_text = sections.get("physical_chemical", {}).get("text", "")
    if not sec9_text:
        for k, v in sections.items():
            if k in ("9","sec9","section9"):
                sec9_text = v.get("text", ""); break
    pc_target_text = sec9_text if sec9_text.strip() else text
    phys_result, phys_log = extract_physchem(pc_target_text)
    if phys_result:
        for k, v in phys_result.items():
            row = {"file": file.name, "key": k}
            if isinstance(v, dict):
                row.update({
                    "raw": v.get("raw",""),
                    "value": v.get("value",""),
                    "low": v.get("low",""),
                    "high": v.get("high",""),
                    "cmp": v.get("cmp",""),
                    "unit": v.get("unit",""),
                })
            agg_phys.append(row)

    # 섹션15: 규제사항
    legal_df = pd.DataFrame()
    try:
        legal_rows = build_legal_table(text)
        legal_df = pd.DataFrame(legal_rows)
        if not legal_df.empty:
            legal_df["file"] = file.name
            agg_legal.append(legal_df)
    except Exception:
        pass

    # GHS 그림문자
    ghs_details, picto_list = [], []
    try:
        ghs_details = map_hcodes_to_pictos_detailed(H) if H else []
        picto_list = [d.get("pictogram") for d in ghs_details] if ghs_details else []
    except Exception:
        pass

    # 메타(제품명/회사/MSDS No/대표 CAS)
    meta = extract_meta(text, sections)
    meta["file"]       = file.name
    meta["text_source"]= text_src
    meta["auto_len"]   = len_auto
    meta["visual_len"] = len_visual
    meta["header_score_auto"]   = score_auto
    meta["header_score_visual"] = score_visual
    meta["overlap"]    = f"{overlap:.2f}"
    agg_meta.append(meta)

    # 요약 행
    summary_rows.append({
        "file": file.name,
        "product_name": meta.get("product_name",""),
        "supplier": meta.get("supplier",""),
        "msds_no": meta.get("msds_no",""),
        "representative_cas": meta.get("representative_cas",""),
        "text_source": text_src,
        "H_count": len(H),
        "P_count": len(P),
        "CAS_count": len(CAS),
        "hazard_class_rows": (0 if hz_df.empty else len(hz_df)),
        "legal_rows": (0 if legal_df.empty else len(legal_df)),
        "pictograms": ", ".join(sorted(set(picto_list))) if picto_list else "-",
    })

    # 파일별 상세(접이식)
    with st.expander(f"📄 {file.name} — 상세 보기", expanded=False):
        st.caption("기본 메타")
        meta_cols = st.columns(4)
        meta_cols[0].metric("제품명", meta.get("product_name","") or "-")
        meta_cols[1].metric("회사/제조사", meta.get("supplier","") or "-")
        meta_cols[2].metric("MSDS/SDS No", meta.get("msds_no","") or "-")
        meta_cols[3].metric("대표 CAS", meta.get("representative_cas","") or "-")
        st.caption(f"텍스트 소스: {text_src} (auto_len={len_auto}, visual_len={len_visual}, hdr_auto={score_auto}, hdr_visual={score_visual}, overlap≈{overlap:.2f})")

        c1, c2 = st.columns(2)
        with c1:
            st.caption("유해‧위험문구(H) 전체")
            st.text_area(f"H-lines-{file.name}", hp_simple.get("hazard_text","") or "(없음)", height=200, key=f"h_{file.name}")
        with c2:
            st.caption("예방조치문구(P) 전체")
            st.text_area(f"P-lines-{file.name}", hp_simple.get("precaution_text","") or "(없음)", height=200, key=f"p_{file.name}")

        st.caption("섹션2 분류/구분")
        if not hz_df.empty:
            st.dataframe(hz_df, use_container_width=True, hide_index=True)
        else:
            st.info("분류/구분 항목 없음")

        st.caption("섹션3 구성성분")
        if not comp_df.empty:
            st.dataframe(comp_df, use_container_width=True, hide_index=True)
        else:
            st.info("구성성분 표를 찾지 못했습니다.")

        st.caption("섹션9 물리·화학 (핵심 추출)")
        phys_df_one = pd.DataFrame([r for r in agg_phys if r.get("file")==file.name])
        if not phys_df_one.empty:
            st.dataframe(phys_df_one, use_container_width=True, hide_index=True)
        else:
            st.info("섹션 9에서 추출된 항목 없음")

        st.caption("섹션15 규제사항")
        if not legal_df.empty:
            st.dataframe(legal_df, use_container_width=True, hide_index=True)
        else:
            st.info("규제사항 항목 없음")

        if ghs_details:
            st.caption("GHS 그림문자")
            cols = st.columns(min(4, len(ghs_details)))
            for i, item in enumerate(ghs_details):
                p = item["pictogram"]; img_path = os.path.join(IMAGE_DIR, f"{p}.gif")
                with cols[i % len(cols)]:
                    try:
                        st.image(img_path, width=80, caption=p)
                    except Exception:
                        st.write(p)

    # HP 라인 통합
    if hp_simple.get("hazard_text"):
        agg_hp_lines.append({"file": file.name, "type": "H", "text": hp_simple["hazard_text"]})
    if hp_simple.get("precaution_text"):
        agg_hp_lines.append({"file": file.name, "type": "P", "text": hp_simple["precaution_text"]})

    progress.progress(idx / len(files))

# ------------------ 전체 집계 ------------------
st.subheader("📊 전체 요약 / Summary")
summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, use_container_width=True, hide_index=True)
st.download_button("CSV 다운로드 (요약)", data=_csv_bytes(summary_df),
                   file_name="summary_msds_batch.csv", mime="text/csv")

st.subheader("메타 통합 (제품명/회사/MSDS No/CAS/텍스트소스)")
meta_df = pd.DataFrame(agg_meta)
if not meta_df.empty:
    st.dataframe(meta_df, use_container_width=True, hide_index=True)
    st.download_button("CSV 다운로드 (메타 통합)", data=_csv_bytes(meta_df),
                       file_name="meta_all.csv", mime="text/csv")
else:
    st.info("메타 데이터가 없습니다.")

st.subheader("섹션 3 통합 표 (구성성분)")
if agg_comp:
    all_comp = pd.concat(agg_comp, ignore_index=True)
    st.dataframe(all_comp, use_container_width=True, hide_index=True)
    st.download_button("CSV 다운로드 (섹션3 통합)", data=_csv_bytes(all_comp),
                       file_name="sec3_composition_all.csv", mime="text/csv")
else:
    st.info("섹션 3 데이터가 없습니다.")

st.subheader("섹션 2 통합 표 (분류/구분)")
if agg_hazard:
    all_hz = pd.concat(agg_hazard, ignore_index=True)
    st.dataframe(all_hz, use_container_width=True, hide_index=True)
    st.download_button("CSV 다운로드 (섹션2 통합)", data=_csv_bytes(all_hz),
                       file_name="sec2_hazard_classes_all.csv", mime="text/csv")
else:
    st.info("섹션 2 분류/구분 데이터가 없습니다.")

st.subheader("섹션 9 통합 표 (물리·화학 핵심)")
if agg_phys:
    all_phys = pd.DataFrame(agg_phys)
    st.dataframe(all_phys, use_container_width=True, hide_index=True)
    st.download_button("CSV 다운로드 (섹션9 통합)", data=_csv_bytes(all_phys),
                       file_name="sec9_physchem_all.csv", mime="text/csv")
else:
    st.info("섹션 9 데이터가 없습니다.")

st.subheader("섹션 15 통합 표 (규제사항)")
if agg_legal:
    all_legal = pd.concat(agg_legal, ignore_index=True)
    st.dataframe(all_legal, use_container_width=True, hide_index=True)
    st.download_button("CSV 다운로드 (섹션15 통합)", data=_csv_bytes(all_legal),
                       file_name="sec15_legal_items_all.csv", mime="text/csv")
else:
    st.info("섹션 15 데이터가 없습니다.")

st.subheader("H/P 라인 통합 (원문 줄 묶음)")
if agg_hp_lines:
    hp_df = pd.DataFrame(agg_hp_lines)
    st.dataframe(hp_df, use_container_width=True, hide_index=True)
    st.download_button(
        "TXT 다운로드 (H-lines 전체, 파일별 병합)",
        data="\n\n".join([f"[{r['file']}] H-lines\n{r['text']}" for r in hp_df.query("type=='H'").to_dict('records')]).encode("utf-8-sig"),
        file_name="all_H_lines.txt", mime="text/plain"
    )
    st.download_button(
        "TXT 다운로드 (P-lines 전체, 파일별 병합)",
        data="\n\n".join([f"[{r['file']}] P-lines\n{r['text']}" for r in hp_df.query("type=='P'").to_dict('records')]).encode("utf-8-sig"),
        file_name="all_P_lines.txt", mime="text/plain"
    )
else:
    st.info("H/P 라인 데이터가 없습니다.")
