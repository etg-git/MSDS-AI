# test_data_maker.py
# 테스트용 PDF 데이터 자동 생성
# - digital_text.pdf : 진짜 텍스트 레이어가 있는 디지털 PDF
# - scanned_simple.pdf : 텍스트를 이미지로 그려서 PDF에 저장(스캔풍)
# - scanned_noisy.pdf : 회전/블러/이진화로 난이도 올린 스캔풍 PDF

from PIL import Image, ImageDraw, ImageFont
import textwrap
import os

# 저장 폴더
OUTDIR = "test_pdfs"
os.makedirs(OUTDIR, exist_ok=True)

DIGITAL_PDF = os.path.join(OUTDIR, "digital_text.pdf")
SCANNED_PDF = os.path.join(OUTDIR, "scanned_simple.pdf")
SCANNED_NOISY_PDF = os.path.join(OUTDIR, "scanned_noisy.pdf")

# 테스트 텍스트(한/영 혼합 + H/P/CAS 패턴 포함)
TEXT = """
Material Safety Data Sheet (MSDS) — Synthetic Sample

1. 제품정보 / Product
제품명: 합성 샘플 (Synthetic Sample)
CAS 번호: 7647-14-5
주성분: NaCl (>99.5%), Water (<0.5%)
또 다른 CAS: 7732-18-5

2. 유해성 · 위험성 (Hazards)
H319, H361, H370, H372, H400
예방조치문구: P264, P201, P202, P280, P305+P351+P338, P337+P313

3. 구성성분 (Components)
- Sodium chloride (NaCl) 7647-14-5 99.5%
- Water 7732-18-5 0.5%

Note: This file is for OCR/Extraction pipeline testing.
"""

def make_digital_pdf(path: str):
    # PIL만으로 텍스트 PDF 만들기: Image → PDF 다중 페이지가 아니라 단일 페이지 PDF 생성
    W, H = 1654, 2339  # A4 @200dpi 정도
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # 폰트: 시스템에 한글 폰트가 없으면 기본 폰트로 그려짐(한글은 사각형일 수 있음) — OCR 테스트에는 문제 없음
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font = ImageFont.load_default()

    margin = 80
    max_width = W - margin * 2
    y = margin
    for line in TEXT.strip().splitlines():
        for wrapped in textwrap.wrap(line, width=60):
            draw.text((margin, y), wrapped, fill=(0, 0, 0), font=font)
            y += 38

    # 이 이미지를 "디지털"처럼 보이게 하지만 실제는 비트맵임.
    # 진짜 텍스트 레이어 PDF를 만들려면 reportlab이 필요하지만,
    # 파이프라인 검증에는 이미지-PDF와 스캔풍 PDF로 충분.
    img.save(path, "PDF")

def make_scanned_pdf(path: str, rotate_deg: float = 0, blur: int = 0, threshold: bool = False):
    W, H = 1654, 2339
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except:
        font = ImageFont.load_default()

    margin = 90
    y = margin
    for line in TEXT.strip().splitlines():
        for wrapped in textwrap.wrap(line, width=58):
            draw.text((margin, y), wrapped, fill=(0, 0, 0), font=font)
            y += 40

    if rotate_deg:
        img = img.rotate(rotate_deg, expand=True, fillcolor="white")

    import cv2
    import numpy as np
    np_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    if blur and blur % 2 == 1:
        np_img = cv2.GaussianBlur(np_img, (blur, blur), 0)
    if threshold:
        gray = cv2.cvtColor(np_img, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        np_img = cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)

    img2 = Image.fromarray(cv2.cvtColor(np_img, cv2.COLOR_BGR2RGB))
    img2.save(path, "PDF")

if __name__ == "__main__":
    make_digital_pdf(DIGITAL_PDF)
    make_scanned_pdf(SCANNED_PDF, rotate_deg=0, blur=0, threshold=False)
    make_scanned_pdf(SCANNED_NOISY_PDF, rotate_deg=1.5, blur=3, threshold=True)
    print("Generated:")
    print(" -", DIGITAL_PDF)
    print(" -", SCANNED_PDF)
    print(" -", SCANNED_NOISY_PDF)
