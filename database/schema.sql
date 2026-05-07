-- Punjab & Haryana Legal AI — Supabase Schema
-- Run this in the Supabase SQL editor before running 07_load_to_supabase.py

-- Enable required extensions
create extension if not exists "uuid-ossp";
create extension if not exists "pg_trgm";  -- for fuzzy text search


-- ── Cases ─────────────────────────────────────────────────────────────────────

create table if not exists cases (
    id                  uuid primary key default uuid_generate_v4(),
    doc_id              text unique not null,
    case_id             text,

    -- Identifiers
    case_number         text,
    case_title          text,
    court               text default 'High Court of Punjab and Haryana at Chandigarh',

    -- Classification
    category            text,          -- internal key e.g. bail_regular
    category_label      text,          -- display label e.g. Regular Bail
    case_category       text,          -- AI extracted e.g. NDPS Bail
    petition_type       text,

    -- People
    judge               text,
    bench               text[],
    petitioner          text,
    respondent          text,
    advocate_petitioner text,
    advocate_respondent text,

    -- FIR details (criminal matters)
    fir_number          text,
    fir_date            date,
    police_station      text,
    district            text,

    -- Case details
    sections            text[],
    acts                text[],
    outcome             text,
    decision_date       date,

    -- AI summary fields
    summary_case_type       text,
    summary_facts           text,
    summary_legal_issue     text,
    summary_final_outcome   text,
    summary_why_useful      text,
    petitioners_arguments   text[],
    respondents_arguments   text[],
    courts_reasoning        text[],
    directions              text[],

    -- Search
    search_tags         text[],

    -- Indian Kanoon metadata
    ik_title            text,
    ik_docsource        text,
    ik_publish_date     date,
    ik_cite_list        jsonb default '[]',
    ik_cited_by         jsonb default '[]',

    -- Timestamps
    created_at          timestamptz default now(),
    updated_at          timestamptz default now()
);

-- Full text search vector (trigger-based to avoid immutability constraint)
alter table cases add column if not exists fts tsvector;

create or replace function cases_fts_update() returns trigger as $$
begin
    new.fts := to_tsvector('english',
        coalesce(new.case_number, '') || ' ' ||
        coalesce(new.case_title, '') || ' ' ||
        coalesce(new.case_category, '') || ' ' ||
        coalesce(new.judge, '') || ' ' ||
        coalesce(new.petitioner, '') || ' ' ||
        coalesce(new.respondent, '') || ' ' ||
        coalesce(new.advocate_petitioner, '') || ' ' ||
        coalesce(new.advocate_respondent, '') || ' ' ||
        coalesce(new.police_station, '') || ' ' ||
        coalesce(new.district, '') || ' ' ||
        coalesce(new.fir_number, '') || ' ' ||
        coalesce(new.summary_facts, '') || ' ' ||
        coalesce(new.summary_legal_issue, '') || ' ' ||
        coalesce(array_to_string(new.sections, ' '), '') || ' ' ||
        coalesce(array_to_string(new.search_tags, ' '), '')
    );
    return new;
end;
$$ language plpgsql;

create trigger cases_fts_trigger
    before insert or update on cases
    for each row execute function cases_fts_update();

create index if not exists cases_fts_idx on cases using gin(fts);
create index if not exists cases_case_number_idx on cases(case_number);
create index if not exists cases_category_idx on cases(category);
create index if not exists cases_outcome_idx on cases(outcome);
create index if not exists cases_judge_idx on cases(judge);
create index if not exists cases_decision_date_idx on cases(decision_date);
create index if not exists cases_petitioner_trgm on cases using gin(petitioner gin_trgm_ops);
create index if not exists cases_respondent_trgm on cases using gin(respondent gin_trgm_ops);
create index if not exists cases_sections_idx on cases using gin(sections);
create index if not exists cases_search_tags_idx on cases using gin(search_tags);


-- ── Lawyers ───────────────────────────────────────────────────────────────────

create table if not exists lawyers (
    id              uuid primary key default uuid_generate_v4(),
    enrollment      text unique not null,   -- e.g. P/1234/2005
    full_name       text not null,
    email           text unique,
    phone           text,
    last_synced_at  timestamptz,
    created_at      timestamptz default now()
);


-- ── Lawyer <-> Case mapping ───────────────────────────────────────────────────

create table if not exists lawyer_cases (
    lawyer_id   uuid references lawyers(id) on delete cascade,
    case_id     uuid references cases(id) on delete cascade,
    pinned      boolean default false,       -- lawyer explicitly claimed this case
    hidden      boolean default false,       -- lawyer dismissed this case
    created_at  timestamptz default now(),
    primary key (lawyer_id, case_id)
);

create index if not exists lawyer_cases_lawyer_idx on lawyer_cases(lawyer_id);
create index if not exists lawyer_cases_case_idx on lawyer_cases(case_id);


-- ── Saved searches / bookmarks ────────────────────────────────────────────────

create table if not exists saved_cases (
    id          uuid primary key default uuid_generate_v4(),
    lawyer_id   uuid references lawyers(id) on delete cascade,
    case_id     uuid references cases(id) on delete cascade,
    note        text,
    created_at  timestamptz default now(),
    unique (lawyer_id, case_id)
);


-- ── Helper: updated_at trigger ────────────────────────────────────────────────

create or replace function update_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

create trigger cases_updated_at
    before update on cases
    for each row execute function update_updated_at();


-- ── Search function ───────────────────────────────────────────────────────────

create or replace function search_cases(
    query           text default null,
    p_category      text default null,
    p_outcome       text default null,
    p_judge         text default null,
    p_section       text default null,
    p_from_date     date default null,
    p_to_date       date default null,
    p_limit         int default 20,
    p_offset        int default 0
)
returns table (
    id              uuid,
    case_number     text,
    case_title      text,
    case_category   text,
    judge           text,
    decision_date   date,
    outcome         text,
    petitioner      text,
    respondent      text,
    sections        text[],
    search_tags     text[],
    summary_why_useful text,
    rank            float4
)
language sql stable as $$
    select
        c.id,
        c.case_number,
        c.case_title,
        c.case_category,
        c.judge,
        c.decision_date,
        c.outcome,
        c.petitioner,
        c.respondent,
        c.sections,
        c.search_tags,
        c.summary_why_useful,
        case when query is not null
            then ts_rank(c.fts, websearch_to_tsquery('english', query))
            else 1.0
        end as rank
    from cases c
    where
        (query is null or c.fts @@ websearch_to_tsquery('english', query))
        and (p_category is null or c.category = p_category)
        and (p_outcome is null or c.outcome ilike p_outcome)
        and (p_judge is null or c.judge ilike '%' || p_judge || '%')
        and (p_section is null or p_section = any(c.sections))
        and (p_from_date is null or c.decision_date >= p_from_date)
        and (p_to_date is null or c.decision_date <= p_to_date)
    order by rank desc, c.decision_date desc
    limit p_limit
    offset p_offset;
$$;
