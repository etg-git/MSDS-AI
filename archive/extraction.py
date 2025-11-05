import fitz  # PyMuPDF

pdf_path = "/msds/벤젠_msds.pdf"
doc = fitz.open(pdf_path)

# 1) 페이지 전체 텍스트
for i, page in enumerate(doc):
    txt = page.get_text()  # 레이아웃 느슨히 유지한 문자열
    print(f"[page {i+1}] {txt[:300]}...")

# 2) 단어 단위 좌표(bbox) 추출
for i, page in enumerate(doc):
    words = page.get_text("words")  # [x0, y0, x1, y1, "word", block, line, word_no]
    for x0, y0, x1, y1, w, *_ in words[:10]:
        print(f"[p{i+1}] {w} @ ({x0:.1f},{y0:.1f},{x1:.1f},{y1:.1f})")
    break

# 3) 문단/블록 단위로 받기
for i, page in enumerate(doc):
    blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, ...)
    for b in blocks[:3]:
        print("--- block ---")
        print(b[4])
    break

doc.close()
