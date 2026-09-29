#!/usr/bin/env python3
"""
SECOND-PASS scrape for a single date (default: 2026-09-15).

Run:
    python3 second_pass_date15.py            # scrape date 2026-09-15 for the 2nd time
    python3 second_pass_date15.py --date 2026-09-15   # explicit
    python3 second_pass_date15.py --no-scrape          # reuse an existing raw CSV
    python3 second_pass_date15.py --venv /path/to/python  # interpreter used to run the scraper

What it guarantees in the final CSV:
  1. ONLY entries that have NEVER been scraped before — anything already in
     scraped_seen.json (which covers every prior dated CSV, incl. the first
     pass of this date) is skipped by the scraper's cross-run dedup and again
     filtered here by URL + company/role/location keys.
  2. NO job / company / location / URL overlap with ANY other date's output —
     the scraper builds keys from all other dated CSVs at scrape time; this
     script re-checks overlap against those same reference files afterwards.
  3. NO empty fields / rows — rows with any blank cell are dropped.
  4. NO inactive / broken / tracking URLs — every surviving sourceLink is
     re-verified with a HEAD (GET fallback) liveness check in parallel.
"""

import csv
import os
import re
import subprocess
import sys
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor

import job_scraper as js

DATE = "2026-09-15"
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

RAW_OUT = os.path.join(os.path.dirname(__file__), f"jobs_{DATE}_2ndpass_raw.csv")
CLEAN_OUT = os.path.join(os.path.dirname(__file__), f"jobs_{DATE}_2ndpass_clean.csv")
FIELDNAMES = js.REQUESTED_FIELDNAMES


def run_scraper(date_str, interpreter):
    """Launch job_scraper.py for the given date (2nd pass)."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "job_scraper.py")
    cmd = [
        interpreter, script, "--date", date_str,
        "--out", RAW_OUT,
    ]
    print(f"[scrape] {' '.join(cmd)}")
    rc = subprocess.call(cmd)
    if rc != 0:
        raise SystemExit(f"scraper exited with code {rc}")
    if not os.path.exists(RAW_OUT):
        raise SystemExit(f"no output produced: {RAW_OUT}")


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def norm_url(url):
    return js._norm_url(url or "")


def comp_key(row):
    company = (row.get("company") or "").strip().lower()
    role = (row.get("role") or "").strip().lower()
    location = js.normalize_location(row.get("location") or "").lower().strip()
    return f"{company}::{role}::{location}"


def other_date_reference_files(date_str):
    """All dated CSVs for dates OTHER than date_str (first-pass + derived files)."""
    here = os.path.dirname(os.path.abspath(__file__))
    refs = []
    for name in sorted(os.listdir(here)):
        low = name.lower()
        if not low.endswith(".csv"):
            continue
        if name.startswith(".~lock"):
            continue
        base = low[:-4]
        if not (base.startswith("jobs_") or base.startswith("jobs_output_")):
            continue
        m = DATE_RE.search(name)
        if not m:
            continue
        if m.group(1) == date_str:
            continue  # same-date files (raw/derived of this pass) are not "other dates"
        refs.append(os.path.join(here, name))
    return refs


def build_reference_keys(paths):
    """Collect {url} and {company::role::location} keys from reference CSVs."""
    urls, comps = set(), set()
    for path in paths:
        try:
            for row in read_csv(path):
                u = norm_url(row.get("sourceLink"))
                if u:
                    urls.add(u)
                company = (row.get("company") or "").strip().lower()
                role = (row.get("role") or "").strip().lower()
                if company and role:
                    loc = js.normalize_location(row.get("location") or "").lower().strip()
                    comps.add(f"{company}::{role}::{loc}")
        except Exception as e:
            print(f"  [warn] skipping reference file {path}: {e}")
    return urls, comps


def has_empty_field(row):
    return any(not (v or "").strip() for v in row.values())


def main():
    ap = ArgumentParser()
    ap.add_argument("--date", default=DATE)
    ap.add_argument("--no-scrape", action="store_true",
                    help="skip the scrape; use the existing raw CSV if present")
    ap.add_argument("--venv", default=sys.executable,
                    help="python interpreter used to run job_scraper.py")
    args = ap.parse_args()
    date_str = args.date
    global RAW_OUT, CLEAN_OUT
    RAW_OUT = os.path.join(os.path.dirname(__file__), f"jobs_{date_str}_2ndpass_raw.csv")
    CLEAN_OUT = os.path.join(os.path.dirname(__file__), f"jobs_{date_str}_2ndpass_clean.csv")
    if not DATE_RE.match(date_str):
        raise SystemExit(f"bad date: {date_str}")

    if not args.no_scrape:
        run_scraper(date_str, args.venv)

    print(f"[1] reading 2nd-pass raw output: {RAW_OUT}")
    rows = read_csv(RAW_OUT) if os.path.exists(RAW_OUT) else []
    print(f"    {len(rows)} rows")
    if not rows:
        print("    (empty — nothing new this pass)")

    # --- Overlap check against every OTHER date's output ---
    refs = other_date_reference_files(date_str)
    print(f"[2] building overlap keys from {len(refs)} other-date output(s)")
    ref_urls, ref_comps = build_reference_keys(refs)
    kept, overlapped = [], 0
    for row in rows:
        if norm_url(row.get("sourceLink")) in ref_urls or comp_key(row) in ref_comps:
            overlapped += 1
            continue
        kept.append(row)
    print(f"    removed {overlapped} row(s) overlapping other dates, {len(kept)} remain")

    # --- Empty fields / rows ---
    clean, empty_dropped = [], 0
    for row in kept:
        if has_empty_field(row):
            empty_dropped += 1
            continue
        clean.append(row)
    print(f"[3] dropped {empty_dropped} row(s) with empty fields, {len(clean)} remain")

    # --- Inactive / broken URL check (parallel) ---
    print(f"[4] checking {len(clean)} source links for inactive/broken URLs ...")
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

    with open(CLEAN_OUT, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, quoting=csv.QUOTE_ALL,
                                lineterminator="\r\n")
        writer.writeheader()
        for row in alive:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
    print(f"\n[5] FINAL: {len(alive)} NEW, clean row(s) -> {CLEAN_OUT}")
    print(f"    summary: {len(rows)} scraped, -{overlapped} overlap, "
          f"-{empty_dropped} empty, -{dead} broken URL")


if __name__ == "__main__":
    main()