#!/usr/bin/env python3
"""
Combine the two 2026-09-15 scrape runs into one clean final CSV:

  1. The FIRST run's full output is always kept intact (requirement: "all the
     entries that were scraped first").
  2. Jobs from the RE-run are added only when they are truly new (no URL /
     no company+role+location match against the first run).
  3. Everything is checked for overlap against every OTHER date's output
     (URL match first, then company + role + location, with locations
     single-location normalized on both sides) and matching jobs are dropped.
  4. Rows with ANY empty field are dropped.
  5. Rows whose sourceLink is now inactive/broken are dropped (HEAD/GET check).
"""

import csv
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

import job_scraper as js

DATE = "2026-09-15"
FIRST_RUN = os.path.join(os.path.dirname(__file__), "jobs_2026-09-15.csv")
RERUN = os.path.join(os.path.dirname(__file__), "jobs_2026-09-15_rerun.csv")
OUT = os.path.join(os.path.dirname(__file__), "jobs_2026-09-15_combined.csv")
FIELDNAMES = ["company", "role", "platform", "location", "remote", "salaryMin",
              "salaryMax", "seniority", "visaSponsorship", "employmentType",
              "description", "requiredSkills", "tags", "sourceLink", "active"]


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def norm_url(url):
    return js._norm_url(url or "")


def comp_key(row):
    company = (row.get("company") or "").strip().lower()
    role = (row.get("role") or "").strip().lower()
    location = js.normalize_location(row.get("location") or "").lower().strip()
    return f"{company}::{role}::{location}"


def other_date_reference_files():
    """All dated output CSVs for dates OTHER than the one being built."""
    here = os.path.dirname(os.path.abspath(__file__))
    refs = []
    date_re = re.compile(r"(\d{4}-\d{2}-\d{2})")
    for name in sorted(os.listdir(here)):
        low = name.lower()
        if not low.endswith(".csv"):
            continue
        if name.startswith(".~lock"):
            continue
        base = low[:-4]
        if not (base.startswith("jobs_") or base.startswith("jobs_output_")):
            continue
        m = date_re.search(name)
        if not m:
            continue
        if m.group(1) == DATE:
            continue  # same date outputs (first run, rerun, derived) are not "other dates"
        refs.append(os.path.join(here, name))
    return refs


def build_reference_keys(paths):
    urls, comps = set(), set()
    for path in paths:
        try:
            for row in read_csv(path):
                u = norm_url(row.get("sourceLink"))
                if u:
                    urls.add(u)
                company = (row.get("company") or "").strip().lower()
                role = (row.get("role") or "").strip().lower()
                location = js.normalize_location(row.get("location") or "").lower().strip()
                if company and role:
                    comps.add(f"{company}::{role}::{location}")
        except Exception as e:
            print(f"  [warn] skipping reference file {path}: {e}")
    return urls, comps


def has_empty_field(row):
    return any(not (v or "").strip() for v in row.values())


def main():
    print(f"[1] reading first run: {FIRST_RUN}")
    first = read_csv(FIRST_RUN)
    print(f"    {len(first)} rows")

    print(f"[2] reading re-run: {RERUN}")
    rerun = read_csv(RERUN)
    print(f"    {len(rerun)} rows")

    # --- Merge: first-run rows first (kept as-is), then only-new rerun rows ---
    seen_urls, seen_comps = set(), set()
    merged = []
    new_from_rerun = 0
    for src_name, src_rows in (("first", first), ("rerun", rerun)):
        for row in src_rows:
            u = norm_url(row.get("sourceLink"))
            ck = comp_key(row)
            if (u and u in seen_urls) or ck in seen_comps:
                if src_name == "rerun":
                    new_from_rerun -= 0  # counted below
                continue
            seen_urls.add(u)
            seen_comps.add(ck)
            merged.append(row)
            if src_name == "rerun":
                new_from_rerun += 1
    print(f"[3] merged {len(merged)} rows (first-run {len(first)} + {new_from_rerun} new from re-run; "
          f"duplicates suppressed)")

    # --- Cross-date overlap removal ---
    refs = other_date_reference_files()
    print(f"[4] building overlap keys from {len(refs)} other-date output(s):")
    for r in refs:
        print(f"      - {os.path.basename(r)}")
    ref_urls, ref_comps = build_reference_keys(refs)
    kept, overlapped = [], 0
    for row in merged:
        if norm_url(row.get("sourceLink")) in ref_urls or comp_key(row) in ref_comps:
            overlapped += 1
            continue
        kept.append(row)
    print(f"    removed {overlapped} row(s) overlapping other dates, {len(kept)} remain")

    # --- Empty fields ---
    clean, empty_dropped = [], 0
    for row in kept:
        if has_empty_field(row):
            empty_dropped += 1
            continue
        clean.append(row)
    print(f"[5] dropped {empty_dropped} row(s) with empty fields, {len(clean)} remain")

    # --- Broken/inactive URL check (parallel) ---
    print(f"[6] checking {len(clean)} source links for inactive/broken URLs ...")
    urls = sorted({row.get("sourceLink", "").strip() for row in clean if (row.get("sourceLink") or "").strip()})
    with ThreadPoolExecutor(max_workers=8) as ex:
        ok_map = dict(zip(urls, ex.map(js.is_source_link_active, urls)))
    alive, dead = [], 0
    for row in clean:
        if ok_map.get((row.get("sourceLink") or "").strip()):
            alive.append(row)
        else:
            dead += 1
    print(f"    dropped {dead} row(s) with inactive/broken source links, {len(alive)} remain")

    # --- Write final ---
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, quoting=csv.QUOTE_ALL,
                                lineterminator="\r\n")
        writer.writeheader()
        for row in alive:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
    print(f"\n[7] FINAL: {len(alive)} rows written to {OUT}")
    print(f"    summary: first-run kept {len(first)}, +{new_from_rerun} new, "
          f"-{overlapped} overlap, -{empty_dropped} empty, -{dead} broken URL")


if __name__ == "__main__":
    main()