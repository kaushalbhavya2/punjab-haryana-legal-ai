"""
Fetches full judgment text from Indian Kanoon API for each case in the
CSV files produced by 01_collect_case_links.py.
Saves raw API responses (HTML + metadata) as JSON to data/cases/raw/.

Usage:
    python3 scripts/02_download_pdfs.py
    python3 scripts/02_download_pdfs.py --category bail_regular
    python3 scripts/02_download_pdfs.py --limit 50
"""

import requests
import json
import time
import argparse
import os
import csv
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

IK_TOKEN = os.getenv("IK_API_TOKEN")
BASE_URL = "https://api.indiankanoon.org"
LINKS_DIR = Path("data/cases/links")
RAW_DIR = Path("data/cases/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "Authorization": f"Token {IK_TOKEN}",
    "Accept": "application/json",
}


def fetch_document(doc_id):
    r = requests.post(
        f"{BASE_URL}/doc/{doc_id}/",
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def fetch_docmeta(doc_id):
    r = requests.post(
        f"{BASE_URL}/docmeta/{doc_id}/",
        headers=HEADERS,
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def load_cases_from_csv(csv_file):
    cases = []
    with open(csv_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cases.append(row)
    return cases


def already_downloaded(doc_id):
    return (RAW_DIR / f"{doc_id}.json").exists()


def download_case(row):
    doc_id = row["doc_id"]
    output_file = RAW_DIR / f"{doc_id}.json"

    if already_downloaded(doc_id):
        return False

    try:
        doc_data = fetch_document(doc_id)
        meta_data = fetch_docmeta(doc_id)
        time.sleep(0.5)
    except Exception as e:
        print(f"  Failed {doc_id}: {e}")
        return False

    payload = {
        "doc_id": doc_id,
        "case_id": row["case_id"],
        "category": row["category"],
        "category_label": row["category_label"],
        "title": row["title"],
        "docsource": row["docsource"],
        "publish_date": row["publish_date"],
        "doc": doc_data,
        "meta": meta_data,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return True


def get_csv_files(category=None):
    if category:
        path = LINKS_DIR / f"{category}.csv"
        return [path] if path.exists() else []
    return sorted(LINKS_DIR.glob("*.csv"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None, help="Category key (default: all)")
    parser.add_argument("--limit", type=int, default=None, help="Max cases to download")
    args = parser.parse_args()

    csv_files = get_csv_files(args.category)
    if not csv_files:
        print("No CSV files found. Run 01_collect_case_links.py first.")
        return

    total_downloaded = 0
    total_skipped = 0

    for csv_file in csv_files:
        cases = load_cases_from_csv(csv_file)
        print(f"\n[{csv_file.stem}] {len(cases)} cases in CSV")

        for i, row in enumerate(cases):
            if args.limit and total_downloaded >= args.limit:
                print(f"Limit of {args.limit} reached.")
                break

            doc_id = row["doc_id"]
            if already_downloaded(doc_id):
                total_skipped += 1
                continue

            downloaded = download_case(row)
            if downloaded:
                total_downloaded += 1
                print(f"  [{total_downloaded}] Downloaded: {row['title'][:70]}")
                time.sleep(1)
            else:
                total_skipped += 1

    print(f"\nDone. Downloaded: {total_downloaded} | Skipped (already done): {total_skipped}")
    print(f"Raw files in: {RAW_DIR}/")


if __name__ == "__main__":
    main()
