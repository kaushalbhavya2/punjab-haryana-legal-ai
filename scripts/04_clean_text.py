"""
Cleans raw extracted text from 03_extract_text.py:
- Normalises whitespace
- Removes page number artifacts (e.g. "1 of 12", "::: Downloaded on ...")
- Fixes common OCR/encoding artifacts
- Decodes HTML entities (&amp; &quot; &#x27; etc.)
- Saves cleaned output to data/cases/cleaned/

Usage:
    python3 scripts/04_clean_text.py
    python3 scripts/04_clean_text.py --category bail_regular
"""

import json
import re
import argparse
from html import unescape
from pathlib import Path


TEXT_DIR = Path("data/cases/text")
CLEANED_DIR = Path("data/cases/cleaned")
CLEANED_DIR.mkdir(parents=True, exist_ok=True)


# Patterns that are layout/download artifacts, not judgment content
ARTIFACT_PATTERNS = [
    r"\d+\s+of\s+\d+",                          # "1 of 12" page markers
    r":::\s*Downloaded on.*?:::",                # Download timestamps
    r"Uploaded by.*?\n",                         # Upload metadata
    r"\(O&M\)",                                  # Case suffix noise
    r"IN THE HIGH COURT OF PUNJAB AND HARYANA",  # Repeated header (kept once)
    r"AT CHANDIGARH\s*\*+",                      # Repeated subheader
]

ARTIFACT_RE = re.compile("|".join(ARTIFACT_PATTERNS), re.IGNORECASE)


def clean_text(raw_text):
    text = unescape(raw_text)

    # Remove artifact patterns
    text = ARTIFACT_RE.sub(" ", text)

    # Collapse multiple spaces and newlines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove lines that are just whitespace or single chars
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if len(line) > 1]
    text = "\n".join(lines)

    return text.strip()


def already_cleaned(doc_id):
    return (CLEANED_DIR / f"{doc_id}.json").exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    text_files = sorted(TEXT_DIR.glob("*.json"))
    if not text_files:
        print("No text files found. Run 03_extract_text.py first.")
        return

    done = 0
    skipped = 0

    for text_path in text_files:
        doc_id = text_path.stem

        if already_cleaned(doc_id):
            skipped += 1
            continue

        with open(text_path, encoding="utf-8") as f:
            data = json.load(f)

        if args.category and data.get("category") != args.category:
            skipped += 1
            continue

        cleaned = clean_text(data.get("raw_text", ""))

        output = {**data, "cleaned_text": cleaned}
        output.pop("raw_text", None)  # don't duplicate storage

        out_path = CLEANED_DIR / f"{doc_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        done += 1
        print(f"  [{done}] Cleaned: {data['title'][:70]}")

    print(f"\nDone. Cleaned: {done} | Skipped: {skipped}")
    print(f"Cleaned files in: {CLEANED_DIR}/")


if __name__ == "__main__":
    main()
