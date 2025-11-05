# 목적: PDF 페이지마다 디지털/스캔 자동 판별 → 텍스트 추출
# 1) 디지털 텍스트가 있으면 그대로 사용
# 2) 텍스트가 거의 없으면 이미지 렌더링 후 OCR (pytesseract)
# 3) 실패 시 한번 더 전처리 파라미터 바꿔 재시도
from dataclasses import dataclass, field
from typing import List, Optional
import io
import fitz  # PyMuPDF
from pdf2image import convert_from_bytes
from PIL import Image
import numpy as np
import cv2
import pytesseract

@dataclass
class PageResult:
    page_index: int
    source: str               # "digital" | "ocr" | "hybrid"
    text: str
    is_scanned_guess: bool
    attempts: List[str] = field(default_factory=list)

@dataclass
class ExtractResult:
    pages: List[PageResult]
    merged_text: str
    final_decision_log: List[str] = field(default_factory=list)

def _has_enough_text(s: str, min_len: int = 40) -> bool:
    return len(s.strip()) >= min_len

def _ocr_pil(pil_img: Image.Image, lang: str, psm: int, oem: int, tessdata_dir: Optional[str]) -> str:
    cfg = f"--oem {oem} --psm {psm}"
    if tessdata_dir:
        cfg += f' --tessdata-dir "{tessdata_dir}"'
    return pytesseract.image_to_string(pil_img, lang=lang, config=cfg)

def _preprocess(np_bgr: np.ndarray, scale=1.5, blur=3, adaptive=True, block=31, C=10) -> np.ndarray:
    out = np_bgr
    if scale and scale != 1.0:
        h, w = out.shape[:2]
        out = cv2.resize(out, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    if blur and blur % 2 == 1:
        gray = cv2.GaussianBlur(gray, (blur, blur), 0)
    if adaptive:
        th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY, block, C)
    else:
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)

def extract_pdf_text_auto(file_bytes: bytes, dpi=300, lang="kor+eng", tessdata_dir: Optional[str]=None) -> ExtractResult:
    pages: List[PageResult] = []
    final_logs: List[str] = []

    doc = fitz.open(stream=file_bytes, filetype="pdf")

    # 1차: 페이지별 디지털 텍스트 확인
    digital_texts = []
    for i in range(len(doc)):
        t = doc[i].get_text()
        digital_texts.append(t)

    # 2차: 이미지 렌더링(OCR 필요 시)
    # pdf2image 우선, 실패 시 PyMuPDF 렌더링
    try:
        images = convert_from_bytes(file_bytes, dpi=dpi)
    except Exception:
        images = []
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for i in range(len(doc)):
            pix = doc[i].get_pixmap(matrix=mat, alpha=False)
            pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(pil)

    for i, page in enumerate(doc):
        raw = digital_texts[i] or ""
        attempts = []
        if _has_enough_text(raw):
            pages.append(PageResult(i, "digital", raw, False, ["digital ok"]))
            continue

        # 스캔본 추정 → OCR
        is_scanned = True
        pil = images[i]
        # 1차 OCR
        attempts.append("ocr psm6 oem3 adaptive")
        txt = _ocr_pil(pil, lang=lang, psm=6, oem=3, tessdata_dir=tessdata_dir).strip()

        # 실패 시 재전처리 후 재시도
        if not _has_enough_text(txt, 10):
            attempts.append("ocr psm4 oem3 adaptive+resize")
            np_bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            proc = _preprocess(np_bgr, scale=1.8, blur=3, adaptive=True, block=31, C=10)
            pil2 = Image.fromarray(cv2.cvtColor(proc, cv2.COLOR_BGR2RGB))
            txt = _ocr_pil(pil2, lang=lang, psm=4, oem=3, tessdata_dir=tessdata_dir).strip()

        pages.append(PageResult(i, "ocr", txt, is_scanned, attempts))

    merged = "\n\n".join(p.text for p in pages)
    # 최종판단 로그
    if any(p.source == "ocr" for p in pages):
        final_logs.append("일부/전체 페이지에서 스캔본으로 판정되어 OCR을 수행했습니다.")
    else:
        final_logs.append("디지털 텍스트가 충분하여 OCR 없이 추출했습니다.")
    return ExtractResult(pages=pages, merged_text=merged, final_decision_log=final_logs)
