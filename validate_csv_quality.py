#!/usr/bin/env python3
"""Validate job CSV outputs for overlap, empty cells, multi-location cells,
   and broken/inactive source links.

Example:
    python3 validate_csv_quality.py --target jobs_2026-09-16.csv
    python3 validate_csv_quality.py
"""

import argparse
import csv
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List, Set, Tuple

import pandas as pd

import job_scraper as js


DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def candidate_csvs(root: str) -> List[str]:
    names = []
    for name in sorted(os.listdir(root)):
        if not name.lower().endswith(".csv"):
            continue
        if name.startswith(".~lock"):
            continue
        low = name.lower()
        if low.startswith("jobs_") or low.startswith("jobs_output_"):
            names.append(name)
    return names


def norm_url(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if hasattr(js, "_norm_url"):
        try:
            return js._norm_url(s)
        except Exception:
            pass
    return s.lower()


def has_empty_field(row) -> bool:
    for v in row.values():
        if v is None:
            return True
        if str(v).strip() == "":
            return True
    return False


def has_multiple_locations(val) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    if not s:
        return False
    if re.search(r"\s*(?:;|(?:\s\|\s)|\s/\s)\s*", s):
        return True
    if re.search(r"\s+(?:and|or)\s+", s, flags=re.IGNORECASE):
        return True
    return False


def row_key(row) -> str:
    company = (row.get("company") or "").strip().lower()
    role = (row.get("role") or "").strip().lower()
    location = js.normalize_location(row.get("location") or "").lower().strip()
    return f"{company}::{role}::{location}"


def read_csv_rows(path: str):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def build_reference_sets(paths: Iterable[str]) -> Tuple[Set[str], Set[str]]:
    ref_urls: Set[str] = set()
    ref_keys: Set[str] = set()
    for path in paths:
        try:
            for row in read_csv_rows(path):
                u = norm_url(row.get("sourceLink") or row.get("url") or "")
                if u:
                    ref_urls.add(u)
                company = (row.get("company") or "").strip().lower()
                role = (row.get("role") or "").strip().lower()
                if company and role:
                    loc = js.normalize_location(row.get("location") or "").lower().strip()
                    ref_keys.add(f"{company}::{role}::{loc}")
        except Exception:
            continue
    return ref_urls, ref_keys


def validate_file(path: str, refs: Tuple[Set[str], Set[str]]) -> dict:
    rows = read_csv_rows(path)
    ref_urls, ref_keys = refs

    empty_rows = []
    multi_location_rows = []
    overlap_rows = []
    bad_url_rows = []
    inactive_url_rows = []

    for idx, row in enumerate(rows):
        if has_empty_field(row):
            empty_rows.append(idx)

        loc = row.get("location") or ""
        if has_multiple_locations(loc):
            multi_location_rows.append((idx, str(loc)))

        u = row.get("sourceLink") or row.get("url") or ""
        url_norm = norm_url(u)
        if not url_norm:
            bad_url_rows.append((idx, "missing"))
        elif not url_norm.startswith(("http://", "https://")):
            bad_url_rows.append((idx, str(u)[:160]))

        if url_norm:
            if norm_url(u) in ref_urls:
                overlap_rows.append((idx, "url", str(u)[:180]))
            elif row_key(row) in ref_keys:
                overlap_rows.append((idx, "company+role+location", row_key(row)))

    # URL activity check separately with a bound executor to keep it safe.
    url_list = []
    for row in rows:
        u = row.get("sourceLink") or row.get("url") or ""
        if isinstance(u, str) and u.strip():
            url_list.append(u.strip())
    url_list = sorted(set(url_list))

    ok_map = {}
    if url_list:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for url, ok in zip(url_list, ex.map(js.is_source_link_active, url_list)):
                ok_map[url] = ok

    for idx, row in enumerate(rows):
        u = row.get("sourceLink") or row.get("url") or ""
        if isinstance(u, str) and u.strip() and not ok_map.get(u.strip(), False):
            inactive_url_rows.append((idx, str(u)[:180]))

    return {
        "path": path,
        "rows": len(rows),
        "empty_rows": empty_rows,
        "multi_location_rows": multi_location_rows,
        "overlap_rows": overlap_rows,
        "bad_url_rows": bad_url_rows,
        "inactive_url_rows": inactive_url_rows,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate output CSV files against project quality rules.")
    parser.add_argument("--target", help="Specific CSV file to validate (defaults to all matched job CSVs)")
    args = parser.parse_args()

    root = os.getcwd()
    csvs = [args.target] if args.target else candidate_csvs(root)
    if args.target and not os.path.exists(args.target):
        print(f"Target file not found: {args.target}")
        return 1

    if not csvs:
        print("No CSV files matched jobs_*.csv or jobs_output_*.csv")
        return 1

    all_paths = [os.path.join(root, name) for name in csvs]
    all_results = []
    all_reference_urls: Set[str] = set()
    all_reference_keys: Set[str] = set()

    # Build aggregate reference sets from all files except each target, for per-file overlap checks.
    for p in all_paths:
        try:
            other_paths = [x for x in all_paths if x != p]
            ref_urls, ref_keys = build_reference_sets(other_paths)
            all_reference_urls = all_reference_urls.union(ref_urls)
            all_reference_keys = all_reference_keys.union(ref_keys)
        except Exception:
            pass

    print("CSV quality validation")
    print("=" * 80)
    overall_fail = 0
    for path in all_paths:
        ref_urls, ref_keys = build_reference_sets([x for x in all_paths if x != path])
        result = validate_file(path, (ref_urls, ref_keys))
        all_results.append(result)

        fail = bool(
            result["empty_rows"]
            or result["multi_location_rows"]
            or result["overlap_rows"]
            or result["bad_url_rows"]
            or result["inactive_url_rows"]
        )

        print(f"\nFILE: {os.path.basename(path)}")
        print(f"Rows: {result['rows']}")
        print(f"Empty rows: {len(result['empty_rows'])}")
        print(f"Multi-location rows: {len(result['multi_location_rows'])}")
        print(f"Cross-date overlaps: {len(result['overlap_rows'])}")
        print(f"Bad/missing URLs: {len(result['bad_url_rows'])}")
        print(f"Inactive/broken URLs: {len(result['inactive_url_rows'])}")
        print("STATUS: PASS" if not fail else "STATUS: FAIL")

        if fail:
            overall_fail += 1
            if result["empty_rows"]:
                print("  Empty row indexes:", result["empty_rows"][:10])
            if result["multi_location_rows"]:
                print("  Multi-location row examples:", result["multi_location_rows"][:5])
            if result["overlap_rows"]:
                print("  Overlap samples:", result["overlap_rows"][:5])
            if result["bad_url_rows"]:
                print("  Bad URL samples:", result["bad_url_rows"][:5])
            if result["inactive_url_rows"]:
                print("  Inactive URL samples:", result["inactive_url_rows"][:5])

    print("\n" + "=" * 80)
    print(f"Files checked: {len(all_results)}")
    print(f"Failing files: {overall_fail}")
    return 0 if overall_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
