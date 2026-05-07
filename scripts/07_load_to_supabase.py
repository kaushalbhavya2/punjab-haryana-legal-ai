"""
Loads all extracted metadata JSONs into Supabase.
Reads from data/cases/metadata/ and upserts into the cases table.

Run schema.sql in Supabase SQL editor first.

Usage:
    python3 scripts/07_load_to_supabase.py
    python3 scripts/07_load_to_supabase.py --category bail_regular
    python3 scripts/07_load_to_supabase.py --limit 100
"""

import json
import argparse
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
METADATA_DIR = Path("data/cases/metadata")


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()
    except Exception:
        return None


def build_row(data):
    parties = data.get("parties", {})
    advocates = data.get("advocates", {})
    fir = data.get("fir_details", {})
    summary = data.get("ai_summary", {})

    return {
        "doc_id":                   data.get("doc_id", ""),
        "case_id":                  data.get("case_id", ""),
        "case_number":              data.get("case_number", ""),
        "case_title":               data.get("case_title", ""),
        "court":                    data.get("court", "High Court of Punjab and Haryana at Chandigarh"),
        "category":                 data.get("category", ""),
        "category_label":           data.get("category_label", ""),
        "case_category":            data.get("case_category", ""),
        "petition_type":            data.get("petition_type", ""),
        "judge":                    data.get("judge", ""),
        "bench":                    data.get("bench", []),
        "petitioner":               parties.get("petitioner", ""),
        "respondent":               parties.get("respondent", ""),
        "advocate_petitioner":      advocates.get("petitioner", ""),
        "advocate_respondent":      advocates.get("respondent", ""),
        "fir_number":               fir.get("fir_number", "") or None,
        "fir_date":                 parse_date(fir.get("fir_date", "")),
        "police_station":           fir.get("police_station", "") or None,
        "district":                 fir.get("district", "") or None,
        "sections":                 data.get("sections", []),
        "acts":                     data.get("acts", []),
        "outcome":                  data.get("outcome", ""),
        "decision_date":            parse_date(data.get("decision_date", "")),
        "summary_case_type":        summary.get("case_type", ""),
        "summary_facts":            summary.get("facts", ""),
        "summary_legal_issue":      summary.get("legal_issue", ""),
        "summary_final_outcome":    summary.get("final_outcome", ""),
        "summary_why_useful":       summary.get("why_useful", ""),
        "petitioners_arguments":    summary.get("petitioners_arguments", []),
        "respondents_arguments":    summary.get("respondents_arguments", []),
        "courts_reasoning":         summary.get("courts_reasoning", []),
        "directions":               summary.get("directions", []),
        "search_tags":              data.get("search_tags", []),
        "ik_title":                 data.get("ik_title", ""),
        "ik_docsource":             data.get("ik_docsource", ""),
        "ik_publish_date":          parse_date(data.get("ik_publish_date", "")),
        "ik_cite_list":             data.get("ik_cite_list", []),
        "ik_cited_by":              data.get("ik_cited_by", []),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY in .env")
        return

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    metadata_files = sorted(METADATA_DIR.glob("*.json"))
    if not metadata_files:
        print("No metadata files found. Run 05_extract_metadata.py first.")
        return

    done = 0
    failed = 0
    batch = []
    BATCH_SIZE = 50

    for path in metadata_files:
        if args.limit and done >= args.limit:
            break

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if args.category and data.get("category") != args.category:
            continue

        try:
            row = build_row(data)
            batch.append(row)
        except Exception as e:
            print(f"  Build row failed {path.stem}: {e}")
            failed += 1
            continue

        if len(batch) >= BATCH_SIZE:
            try:
                supabase.table("cases").upsert(batch, on_conflict="doc_id").execute()
                done += len(batch)
                print(f"  Upserted {done} cases...")
                batch = []
            except Exception as e:
                print(f"  Batch upsert failed: {e}")
                failed += len(batch)
                batch = []

    # Insert remaining
    if batch:
        try:
            supabase.table("cases").upsert(batch, on_conflict="doc_id").execute()
            done += len(batch)
        except Exception as e:
            print(f"  Final batch failed: {e}")
            failed += len(batch)

    print(f"\nDone. Loaded: {done} | Failed: {failed}")


if __name__ == "__main__":
    main()
