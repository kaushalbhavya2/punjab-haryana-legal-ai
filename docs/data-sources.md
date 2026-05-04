# Data Sources

This document tracks the public sources used to collect Punjab & Haryana High Court case data.

## Primary Source

### Punjab & Haryana High Court Official Website

Purpose:

- Collect bail-related judgments/orders
- Store original PDF/source links
- Verify case title, case number, judge name, and decision date

Data to collect:

- Case title
- Case number
- Decision date
- PDF/order link
- Source page URL
- Case category

## First MVP Collection

The first dataset will focus only on bail-related matters.

Initial target:

- 20 bail cases
- Punjab & Haryana High Court only
- Manual collection first
- Automation later

## Collection Rules

For each case, save:

- Original PDF link
- Original source page
- Case title exactly as shown
- Case number exactly as shown
- Decision date
- Notes about bail type, if obvious

## Data Quality Rules

Do not edit legal names casually.

Do not guess missing case details.

If a case field is unclear, leave it blank and add a note.

Always keep the source URL so the record can be verified later.