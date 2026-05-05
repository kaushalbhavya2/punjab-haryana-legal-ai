"""
Sends cleaned judgment text to Claude API and extracts structured metadata
and AI summaries. Saves one JSON file per case to data/cases/metadata/.

Each output JSON contains:
- All case identifiers (case number, court, judge, date, outcome)
- Party and advocate details
- FIR details (where applicable)
- Sections/acts involved
- AI summary (facts, arguments, legal issue, reasoning, outcome, why useful)
- Similar case search tags

Usage:
    python3 scripts/05_extract_metadata.py
    python3 scripts/05_extract_metadata.py --category bail_regular
    python3 scripts/05_extract_metadata.py --limit 10
"""

import json
import re
import time
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv()

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
CLEANED_DIR = Path("data/cases/cleaned")
METADATA_DIR = Path("data/cases/metadata")
METADATA_DIR.mkdir(parents=True, exist_ok=True)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

EXTRACTION_PROMPT = """You are a legal data extraction specialist for the Punjab & Haryana High Court.

Extract structured metadata from the following judgment text. Return ONLY a valid JSON object with no markdown, no explanation.

Required JSON structure:
{{
  "case_number": "",
  "case_title": "",
  "court": "High Court of Punjab and Haryana at Chandigarh",
  "case_category": "",
  "petition_type": "",
  "coram_number": "",
  "judge": "",
  "bench": [],
  "decision_date": "",
  "outcome": "",
  "parties": {{
    "petitioner": "",
    "respondent": ""
  }},
  "advocates": {{
    "petitioner": "",
    "respondent": ""
  }},
  "fir_details": {{
    "fir_number": "",
    "fir_date": "",
    "police_station": "",
    "district": ""
  }},
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
- For case_category use one of: Regular Bail, Anticipatory Bail, NDPS Bail, Civil Writ Petition, Service Matter, Criminal Revision, Criminal Appeal, Regular Second Appeal, Regular First Appeal, First Appeal from Order, Matrimonial, Contempt, Other
- For outcome use one of: Granted, Dismissed, Disposed Of, Withdrawn, Allowed, Partly Allowed, Interim Protection Granted, Notice Issued, Other
- decision_date in YYYY-MM-DD format
- sections should be a list of strings like ["302 IPC", "498A IPC", "108 BNS 2023"]
- search_tags should be 5-10 keywords a lawyer would search (e.g. ["anticipatory bail", "police officer", "absconder", "threatening complainant"])
- If a field is not present in the judgment, use empty string or empty array
- fir_details only applies to criminal matters — leave empty for civil cases
- directions should list any specific directions given by the court beyond the main order

Judgment text:
{text}"""


def extract_metadata(data):
    text = data.get("cleaned_text", "")

    # Truncate to avoid token limits — first 6000 chars covers most judgments
    truncated = text[:6000]

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(text=truncated),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    extracted = json.loads(raw)
    return extracted


def already_extracted(doc_id):
    return (METADATA_DIR / f"{doc_id}.json").exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cleaned_files = sorted(CLEANED_DIR.glob("*.json"))
    if not cleaned_files:
        print("No cleaned files found. Run 04_clean_text.py first.")
        return

    done = 0
    skipped = 0
    failed = 0

    for cleaned_path in cleaned_files:
        if args.limit and done >= args.limit:
            print(f"Limit of {args.limit} reached.")
            break

        doc_id = cleaned_path.stem

        if already_extracted(doc_id):
            skipped += 1
            continue

        with open(cleaned_path, encoding="utf-8") as f:
            data = json.load(f)

        if args.category and data.get("category") != args.category:
            skipped += 1
            continue

        print(f"  Extracting: {data['title'][:70]}")

        try:
            extracted = extract_metadata(data)
        except json.JSONDecodeError as e:
            print(f"    JSON parse failed for {doc_id}: {e}")
            failed += 1
            continue
        except Exception as e:
            print(f"    Failed {doc_id}: {e}")
            failed += 1
            time.sleep(2)
            continue

        output = {
            "doc_id": doc_id,
            "case_id": data["case_id"],
            "category": data["category"],
            "category_label": data["category_label"],
            "ik_title": data["title"],
            "ik_docsource": data["docsource"],
            "ik_publish_date": data["publish_date"],
            "ik_author": data.get("author", ""),
            "ik_bench": data.get("bench", ""),
            "ik_cite_list": data.get("cite_list", []),
            "ik_cited_by": data.get("cited_by", []),
            **extracted,
        }

        out_path = METADATA_DIR / f"{doc_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        done += 1
        print(f"    [{done}] Saved: {extracted.get('case_number', doc_id)}")
        time.sleep(0.5)  # avoid Claude rate limit

    print(f"\nDone. Extracted: {done} | Skipped: {skipped} | Failed: {failed}")
    print(f"Metadata files in: {METADATA_DIR}/")


if __name__ == "__main__":
    main()
