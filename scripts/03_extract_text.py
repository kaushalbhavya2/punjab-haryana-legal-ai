"""
Extracts plain text from raw JSON files produced by 02_download_pdfs.py.
Strips HTML tags from the judgment doc field and saves to data/cases/text/.

Usage:
    python3 scripts/03_extract_text.py
    python3 scripts/03_extract_text.py --category bail_regular
"""

import json
import re
import argparse
from pathlib import Path
from html.parser import HTMLParser


RAW_DIR = Path("data/cases/raw")
TEXT_DIR = Path("data/cases/text")
TEXT_DIR.mkdir(parents=True, exist_ok=True)


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_text(self):
        return " ".join(self.fed)


def strip_html(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_text()


def extract_text_from_raw(raw_path):
    with open(raw_path, encoding="utf-8") as f:
        data = json.load(f)

    doc = data.get("doc", {})
    raw_html = doc.get("doc", "")

    if not raw_html:
        return None

    text = strip_html(raw_html)

    return {
        "doc_id": data["doc_id"],
        "case_id": data["case_id"],
        "category": data["category"],
        "category_label": data["category_label"],
        "title": data["title"],
        "docsource": data["docsource"],
        "publish_date": data["publish_date"],
        "author": doc.get("author", ""),
        "bench": doc.get("bench", ""),
        "cite_list": doc.get("citeList", []),
        "cited_by": doc.get("citedbyList", []),
        "raw_text": text,
    }


def already_extracted(doc_id):
    return (TEXT_DIR / f"{doc_id}.json").exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None)
    args = parser.parse_args()

    raw_files = sorted(RAW_DIR.glob("*.json"))
    if not raw_files:
        print("No raw files found. Run 02_download_pdfs.py first.")
        return

    done = 0
    skipped = 0
    failed = 0

    for raw_path in raw_files:
        doc_id = raw_path.stem

        if already_extracted(doc_id):
            skipped += 1
            continue

        # Filter by category if specified
        if args.category:
            try:
                with open(raw_path) as f:
                    cat = json.load(f).get("category", "")
                if cat != args.category:
                    skipped += 1
                    continue
            except Exception:
                failed += 1
                continue

        try:
            result = extract_text_from_raw(raw_path)
        except Exception as e:
            print(f"  Failed {doc_id}: {e}")
            failed += 1
            continue

        if not result:
            print(f"  Empty doc: {doc_id}")
            failed += 1
            continue

        out_path = TEXT_DIR / f"{doc_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        done += 1
        print(f"  [{done}] Extracted: {result['title'][:70]}")

    print(f"\nDone. Extracted: {done} | Skipped: {skipped} | Failed: {failed}")
    print(f"Text files in: {TEXT_DIR}/")


if __name__ == "__main__":
    main()
