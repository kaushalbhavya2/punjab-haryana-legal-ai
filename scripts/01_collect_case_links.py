"""
Searches Indian Kanoon API for PHHC cases across all major case categories
and saves results to CSV files in data/cases/links/.

Usage:
    python3 scripts/01_collect_case_links.py
    python3 scripts/01_collect_case_links.py --category bail_regular --pages 10
    python3 scripts/01_collect_case_links.py --category all --pages 5
"""

import requests
import csv
import time
import argparse
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

IK_TOKEN = os.getenv("IK_API_TOKEN")
BASE_URL = "https://api.indiankanoon.org"
LINKS_DIR = Path("data/cases/links")
LINKS_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "Authorization": f"Token {IK_TOKEN}",
    "Accept": "application/json",
}

CATEGORIES = {
    "bail_regular": {
        "label": "Regular Bail",
        "query": "regular bail CRM-M doctypes:punjab",
    },
    "bail_anticipatory": {
        "label": "Anticipatory Bail",
        "query": "anticipatory bail CRM-M doctypes:punjab",
    },
    "bail_ndps": {
        "label": "NDPS Bail",
        "query": "NDPS bail narcotic doctypes:punjab",
    },
    "cwp": {
        "label": "Civil Writ Petition",
        "query": "civil writ petition CWP doctypes:punjab",
    },
    "cwp_service": {
        "label": "Service Matter (CWP)",
        "query": "service matter writ petition CWP doctypes:punjab",
    },
    "crr": {
        "label": "Criminal Revision",
        "query": "criminal revision CRR doctypes:punjab",
    },
    "cra": {
        "label": "Criminal Appeal",
        "query": "criminal appeal CRA doctypes:punjab",
    },
    "rsa": {
        "label": "Regular Second Appeal",
        "query": "regular second appeal RSA doctypes:punjab",
    },
    "rfa": {
        "label": "Regular First Appeal",
        "query": "regular first appeal RFA doctypes:punjab",
    },
    "fao": {
        "label": "First Appeal from Order",
        "query": "first appeal order FAO doctypes:punjab",
    },
    "matrimonial": {
        "label": "Matrimonial",
        "query": "matrimonial divorce FAO doctypes:punjab",
    },
    "contempt": {
        "label": "Contempt",
        "query": "contempt of court CCP doctypes:punjab",
    },
}

CSV_FIELDS = [
    "case_id", "title", "docsource", "publish_date",
    "doc_id", "category", "category_label", "headline",
    "docsize", "collected_at",
]


def search_cases(query, pagenum=0):
    r = requests.post(
        f"{BASE_URL}/search/",
        headers=HEADERS,
        data={"formInput": query, "pagenum": pagenum},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def collect_category(category_key, max_pages=5):
    cat = CATEGORIES[category_key]
    label = cat["label"]
    query = cat["query"]
    output_file = LINKS_DIR / f"{category_key}.csv"

    existing_ids = set()
    if output_file.exists():
        with open(output_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(row["doc_id"])

    print(f"\n[{label}] Searching: {query}")

    new_rows = []
    for page in range(max_pages):
        try:
            data = search_cases(query, pagenum=page)
        except Exception as e:
            print(f"  Page {page} failed: {e}")
            break

        docs = data.get("docs", [])
        if not docs:
            print(f"  No more results at page {page}")
            break

        found = data.get("found", "?")
        print(f"  Page {page}: {len(docs)} docs (total found: {found})")

        for doc in docs:
            doc_id = str(doc.get("tid", ""))
            if doc_id in existing_ids:
                continue

            new_rows.append({
                "case_id": f"{category_key}_{doc_id}",
                "title": doc.get("title", ""),
                "docsource": doc.get("docsource", ""),
                "publish_date": doc.get("publishdate", ""),
                "doc_id": doc_id,
                "category": category_key,
                "category_label": label,
                "headline": doc.get("headline", "").replace("\n", " "),
                "docsize": doc.get("docsize", ""),
                "collected_at": datetime.now().isoformat(),
            })
            existing_ids.add(doc_id)

        time.sleep(1)

    if new_rows:
        write_header = not output_file.exists() or output_file.stat().st_size == 0
        with open(output_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerows(new_rows)
        print(f"  Saved {len(new_rows)} new cases -> {output_file}")
    else:
        print(f"  No new cases found")

    return len(new_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--category",
        default="all",
        help=f"Category key or 'all'. Options: {', '.join(CATEGORIES.keys())}",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Pages to fetch per category (10 results per page)",
    )
    args = parser.parse_args()

    categories = (
        list(CATEGORIES.keys())
        if args.category == "all"
        else [args.category]
    )

    total = 0
    for cat_key in categories:
        if cat_key not in CATEGORIES:
            print(f"Unknown category: {cat_key}")
            continue
        total += collect_category(cat_key, max_pages=args.pages)

    print(f"\nDone. Total new cases collected: {total}")
    print(f"CSV files in: {LINKS_DIR}/")


if __name__ == "__main__":
    main()
