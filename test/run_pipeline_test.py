# run_pipeline_test.py
# extract_pdf_text_auto 파이프라인 테스트 러너

import re
from pathlib import Path
from msds_text_extractor import extract_pdf_text_auto

CAS_RE = r"\b(\d{2,7}-\d{2}-\d)\b"
H_RE = r"\bH\d{3}[A-Z]?\b"
P_RE = r"\bP\d{3}[A-Z]?(?:\+P\d{3}[A-Z]?)?\b"

TEST_DIR = Path("test_pdfs")
FILES = [
    TEST_DIR / "digital_text.pdf",
    TEST_DIR / "scanned_simple.pdf",
    TEST_DIR / "scanned_noisy.pdf",
]

def summarize(text: str) -> dict:
    H = sorted(set(re.findall(H_RE, text)))
    P = sorted(set(re.findall(P_RE, text)))
    CAS = sorted(set(re.findall(CAS_RE, text)))
    return {"H": H, "P": P, "CAS": CAS}

if __name__ == "__main__":
    for f in FILES:
        if not f.exists():
            print(f"[skip] {f} not found. Run test_data_maker.py first.")
            continue
        print("\n=== TEST:", f.name, "===")
        pdf_bytes = f.read_bytes()
        res = extract_pdf_text_auto(pdf_bytes, dpi=300, lang="kor+eng", verbose=True)

        for p in res.pages:
            print(f"\n--- Page {p.page_index+1} ---")
            print("source:", p.source)
            print("decision:", p.decision_reason)
            print("attempts:", " | ".join(p.attempts))
            print("\n[HUMAN LOG]")
            print("\n".join(p.human_log))
