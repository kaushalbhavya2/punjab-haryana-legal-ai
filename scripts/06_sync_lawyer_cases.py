"""
Syncs all available PHHC cases for a lawyer by their advocate name.
Called automatically on signup or manually to refresh a lawyer's case history.

Searches Indian Kanoon by advocate name, downloads judgment text, extracts
text, cleans it, and runs Claude metadata extraction. All cases are tagged
with the lawyer's enrollment number.

Cases from advocates with the same name will also appear — this is intentional.
Lawyers can search by case number for exact results.

Usage:
    python3 scripts/06_sync_lawyer_cases.py --name "Rajesh Gupta" --enrollment "P/1234/2005"
    python3 scripts/06_sync_lawyer_cases.py --name "Anil Bansal" --enrollment "P/5678/2010" --pages 20
"""

import requests
import json
import csv
import time
import re
import argparse
import os
from datetime import datetime
from pathlib import Path
from html import unescape
from html.parser import HTMLParser
from dotenv import load_dotenv
import anthropic

load_dotenv()

IK_TOKEN = os.getenv("IK_API_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
BASE_URL = "https://api.indiankanoon.org"

LAWYERS_DIR = Path("data/lawyers")
LAWYERS_DIR.mkdir(parents=True, exist_ok=True)

IK_HEADERS = {
    "Authorization": f"Token {IK_TOKEN}",
    "Accept": "application/json",
}

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


# ── HTML stripping ────────────────────────────────────────────────────────────

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


ARTIFACT_RE = re.compile(
    r"\d+\s+of\s+\d+|:::\s*Downloaded on.*?:::|Uploaded by.*?\n",
    re.IGNORECASE,
)


def clean_text(raw):
    text = unescape(raw)
    text = ARTIFACT_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 1]
    return "\n".join(lines).strip()


# ── Claude extraction ─────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are a legal data extraction specialist for the Punjab & Haryana High Court.

Extract structured metadata from the following judgment text. Return ONLY a valid JSON object with no markdown, no explanation.

Required JSON structure:
{{
  "case_number": "",
  "case_title": "",
  "court": "High Court of Punjab and Haryana at Chandigarh",
  "case_category": "",
  "petition_type": "",
  "judge": "",
  "bench": [],
  "decision_date": "",
  "outcome": "",
  "parties": {{"petitioner": "", "respondent": ""}},
  "advocates": {{"petitioner": "", "respondent": ""}},
  "fir_details": {{"fir_number": "", "fir_date": "", "police_station": "", "district": ""}},
  "sections": [],
  "acts": [],
  "ai_summary": {{
    "case_type": "",
    "facts": "",
    "petitioners_arguments": [],
    "respondents_arguments": [],
    "legal_issue": "",
    "courts_reasoning": [],
    "final_outcome": "",
    "directions": [],
    "why_useful": ""
  }},
  "search_tags": []
}}

Rules:
- case_category: Regular Bail, Anticipatory Bail, NDPS Bail, Civil Writ Petition, Service Matter, Criminal Revision, Criminal Appeal, Regular Second Appeal, Regular First Appeal, First Appeal from Order, Matrimonial, Contempt, Other
- outcome: Granted, Dismissed, Disposed Of, Withdrawn, Allowed, Partly Allowed, Interim Protection Granted, Notice Issued, Other
- decision_date in YYYY-MM-DD format
- sections as list of strings e.g. ["302 IPC", "498A IPC"]
- search_tags: 5-10 keywords a lawyer would search
- Empty string or empty array for missing fields

Judgment text:
{text}"""


def extract_metadata(text, title):
    truncated = text[:6000]
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=truncated)}],
    )
    raw = message.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


# ── IK API calls ──────────────────────────────────────────────────────────────

def search_advocate_cases(name, pagenum=0):
    r = requests.post(
        f"{BASE_URL}/search/",
        headers=IK_HEADERS,
        data={
            "formInput": f'author:"{name}" doctypes:punjab',
            "pagenum": pagenum,
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def fetch_document(doc_id):
    r = requests.post(
        f"{BASE_URL}/doc/{doc_id}/",
        headers=IK_HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── Main sync ─────────────────────────────────────────────────────────────────

def load_existing_doc_ids(lawyer_dir):
    ids = set()
    metadata_dir = lawyer_dir / "metadata"
    if metadata_dir.exists():
        for f in metadata_dir.glob("*.json"):
            ids.add(f.stem)
    return ids


def sync_lawyer(name, enrollment, max_pages=10):
    safe_enrollment = enrollment.replace("/", "-")
    lawyer_dir = LAWYERS_DIR / safe_enrollment
    (lawyer_dir / "metadata").mkdir(parents=True, exist_ok=True)

    existing_ids = load_existing_doc_ids(lawyer_dir)

    print(f"\nSyncing cases for: {name} ({enrollment})")
    print(f"Already processed: {len(existing_ids)} cases")

    # Save lawyer profile
    profile_path = lawyer_dir / "profile.json"
    profile = {
        "name": name,
        "enrollment": enrollment,
        "last_synced": datetime.now().isoformat(),
    }
    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2)

    total_downloaded = 0
    total_extracted = 0
    summary_rows = []

    for page in range(max_pages):
        try:
            data = search_advocate_cases(name, pagenum=page)
        except Exception as e:
            print(f"  Search page {page} failed: {e}")
            break

        docs = data.get("docs", [])
        if not docs:
            print(f"  No more results at page {page}")
            break

        found = data.get("found", "?")
        print(f"  Page {page}: {len(docs)} cases (total: {found})")

        for doc in docs:
            doc_id = str(doc.get("tid", ""))
            if doc_id in existing_ids:
                continue

            title = doc.get("title", "")
            print(f"    Fetching: {title[:65]}")

            # Download
            try:
                doc_data = fetch_document(doc_id)
                time.sleep(0.5)
            except Exception as e:
                print(f"    Download failed {doc_id}: {e}")
                continue

            # Extract + clean text
            raw_html = doc_data.get("doc", "")
            if not raw_html:
                continue
            cleaned = clean_text(strip_html(raw_html))

            # Claude metadata extraction
            try:
                extracted = extract_metadata(cleaned, title)
            except Exception as e:
                print(f"    Extraction failed {doc_id}: {e}")
                time.sleep(2)
                continue

            # Save metadata
            output = {
                "doc_id": doc_id,
                "enrollment": enrollment,
                "advocate_name": name,
                "ik_title": title,
                "ik_docsource": doc.get("docsource", ""),
                "ik_publish_date": doc.get("publishdate", ""),
                **extracted,
            }

            out_path = lawyer_dir / "metadata" / f"{doc_id}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            summary_rows.append({
                "doc_id": doc_id,
                "case_number": extracted.get("case_number", ""),
                "case_title": extracted.get("case_title", title),
                "case_category": extracted.get("case_category", ""),
                "decision_date": extracted.get("decision_date", ""),
                "outcome": extracted.get("outcome", ""),
                "judge": extracted.get("judge", ""),
            })

            existing_ids.add(doc_id)
            total_downloaded += 1
            total_extracted += 1
            print(f"    Saved: {extracted.get('case_number', doc_id)}")
            time.sleep(0.5)

        time.sleep(1)

    # Save CSV summary for this lawyer
    if summary_rows:
        csv_path = lawyer_dir / "cases.csv"
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
            if write_header:
                writer.writeheader()
            writer.writerows(summary_rows)

    print(f"\nDone. Downloaded & extracted: {total_extracted} new cases")
    print(f"Saved to: {lawyer_dir}/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, help="Advocate name as it appears in court records")
    parser.add_argument("--enrollment", required=True, help="Bar Council enrollment number e.g. P/1234/2005")
    parser.add_argument("--pages", type=int, default=10, help="Max search pages (10 results each)")
    args = parser.parse_args()

    sync_lawyer(
        name=args.name,
        enrollment=args.enrollment,
        max_pages=args.pages,
    )


if __name__ == "__main__":
    main()
