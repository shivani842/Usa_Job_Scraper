#!/usr/bin/env python3
"""
refetch_skills.py
=================
Refills empty `requiredSkills` in a scraped jobs CSV by re-fetching each
posting's source page (sourceLink) and running the taxonomy skill extractor on
the full page text. Also removes rows that overlap earlier scrape dates:

  1. URL first        — a sourceLink seen in any prior date CSV is removed.
  2. then company + role + location — a row whose (company, role, location)
     all match a prior date CSV is removed.

Pages fetched from the same URL are cached under `.{script}.cache/` so reruns
are fast and interrupted runs resume without re-fetching.

Usage:
    python3 refetch_skills.py <input_csv> <output_csv> [--prior CSV ...] [--delay SECONDS]

Examples:
    python3 refetch_skills.py jobs_2026-09-11.csv jobs_2026-09-11_final.csv
    python3 refetch_skills.py jobs_2026-09-11.csv jobs_2026-09-11_final.csv \
        --prior jobs_output_2026-09-07.csv jobs_output_2026-09-08.csv \
        --delay 1.0
"""

import argparse
import csv
import hashlib
import os
import re
import sys
# CSV descriptions are kept in full, so fields can exceed the reader's
# default 128KB limit; lift it.
csv.field_size_limit(sys.maxsize)
import time
from html import unescape as html_unescape

import requests
from bs4 import BeautifulSoup

try:
    from job_scraper import extract_required_skills
except ImportError:
    sys.exit("[error] job_scraper.py must be importable from the same directory "
             "(it provides the taxonomy skill extractor)")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".refetch_skills_cache")
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
TIMEOUT = 25
RETRIES = 1
MAX_TEXT_CHARS = 60000

GREENHOUSE_RE = re.compile(r"job-boards\.greenhouse\.io/([^/]+)/jobs/(\d+)", re.I)
ADZUNA_RE = re.compile(r"adzuna\.com/(?:land/)?ad/(\d+)", re.I)


def normalize_url(url):
    """Return a more fetchable URL when the scraped one is a redirect stub.

    Adzuna `/land/ad/{id}?se=...` landing links are bot-blocked (403), but the
    canonical `/details/{id}?se=...` URL still serves the full ad text (status
    404/410 once the ad expires, with the body still carrying the job content).
    """
    m = ADZUNA_RE.search(url or "")
    if m:
        q = ""
        if "?" in url:
            q = url.split("?", 1)[1]
        base = f"https://www.adzuna.com/details/{m.group(1)}"
        return f"{base}?{q}" if q else base
    return url


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def fetch_session():
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return session


def _url_hash(url):
    return hashlib.sha1(url.encode("utf-8", "ignore")).hexdigest()[:20]


def _cache_path(url):
    return os.path.join(CACHE_DIR, _url_hash(url) + ".txt")


def _cached_text(url):
    path = _cache_path(url)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def _save_cached_text(url, text):
    with open(_cache_path(url), "w", encoding="utf-8") as f:
        f.write(text)


def _strip_boilerplate(text):
    """Remove generic near-empty signing-off text scrapers append to rows."""
    text = re.sub(
        r"\s*The (?:successful |ideal |right |perfect )?candidate will "
        r"(?:design, build, and maintain software systems, collaborate with "
        r"cross-functional teams, and deliver high-quality technical solutions"
        r"|bring relevant expertise to contribute meaningfully[^.]*\.?)\s*",
        " ", text, flags=re.I,
    )
    return text


def fetch_page_text(url, session):
    """Fetch a posting URL and return clean visible text (from cache when possible)."""
    url = normalize_url(url)
    cached = _cached_text(url)
    if cached is not None:
        return cached or None

    html = None
    m = GREENHOUSE_RE.search(url)
    if m:
        board, job_id = m.group(1), m.group(2)
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        try:
            resp = session.get(api_url, timeout=TIMEOUT)
            if resp.ok:
                content = resp.json().get("content", "")
                html = content
        except Exception:
            pass

    if html is None:
        seen_status = None
        for attempt in range(1 + RETRIES):
            try:
                resp = session.get(url, timeout=TIMEOUT, allow_redirects=True)
                seen_status = resp.status_code
                # Parse the body even on a 404/410 that still carries the job
                # text (Adzuna serves expired ads as SEO pages with the full
                # posting content). Everything else must be 2xx.
                if resp.ok or ("adzuna.com" in url and resp.status_code in (404, 410)):
                    html = resp.content.decode("utf-8", "replace")
                    break
                raise requests.HTTPError(f"status {resp.status_code}")
            except Exception as e:
                if attempt >= RETRIES:
                    _save_cached_text(url, "")
                    return None
                time.sleep(1)
                continue

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template", "iframe", "form"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = html_unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _strip_boilerplate(text)[:MAX_TEXT_CHARS]
    _save_cached_text(url, text)
    return text or None


def skills_from_url(url, session):
    """Return comma-separated taxonomy skills found in a posting's page text."""
    text = fetch_page_text(url, session)
    if not text:
        return ""
    found = extract_required_skills(text)
    return ", ".join(found)


# ---------------------------------------------------------------------------
# Overlap handling
# ---------------------------------------------------------------------------

def _norm(value):
    return str(value or "").strip().lower()


def _csv_row_keys(company, role, location, url):
    url_key = f"url::{_norm(url)}"
    composite = f"composite::{_norm(company)}::{_norm(role)}::{_norm(location)}"
    return url_key, composite


def load_prior_keys(prior_paths):
    """Return (url_keys, composite_keys) built from all prior date CSVs."""
    prior_urls, prior_composites = set(), set()
    for path in prior_paths:
        if not os.path.exists(path):
            print(f"[warn] prior file not found, skipping: {path}")
            continue
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or not all(
                        c in reader.fieldnames for c in ("company", "role", "sourceLink")):
                    print(f"[warn] missing expected columns, skipping: {path}")
                    continue
                for row in reader:
                    url = row.get("sourceLink") or row.get("URL") or ""
                    url_key, composite = _csv_row_keys(
                        row.get("company", ""), row.get("role", ""),
                        row.get("location", ""), url)
                    if _norm(url):
                        prior_urls.add(url_key)
                    if _norm(row.get("company", "")) and _norm(row.get("role", "")):
                        prior_composites.add(composite)
        except Exception as e:
            print(f"[warn] could not read {path}: {e}")
    return prior_urls, prior_composites


def is_overlap(row, prior_urls, prior_composites):
    url = row.get("sourceLink") or ""
    url_key, composite = _csv_row_keys(
        row.get("company", ""), row.get("role", ""),
        row.get("location", ""), url)
    if url_key in prior_urls:
        return True
    if composite in prior_composites:
        return True
    return False


def discover_prior_csvs(input_path, output_path, explicit):
    if explicit:
        return [os.path.abspath(p) for p in explicit]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_date = None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(input_path))
    if m:
        input_date = m.group(1)
    candidates = []
    for name in sorted(os.listdir(script_dir)):
        if not name.lower().endswith(".csv"):
            continue
        if name.lower() == "jobs.csv" or name.startswith("jobs_") or name.startswith("jobs_output_"):
            abs_path = os.path.normpath(os.path.join(script_dir, name))
            if abs_path == os.path.normpath(input_path):
                continue
            if abs_path == os.path.normpath(output_path):
                continue
            if name.startswith(".~lock"):
                continue
            if input_date:
                date_m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
                # Derived copies of the date being cleaned (e.g. jobs_YYYY-MM-DD_clean.csv)
                # must not count as prior runs — they contain this same dataset.
                if date_m and date_m.group(1) == input_date:
                    continue
            candidates.append(abs_path)
    return candidates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Refill empty requiredSkills by re-fetching posting pages "
                    "and remove rows overlapping earlier scrape dates.")
    parser.add_argument("input_csv")
    parser.add_argument("output_csv")
    parser.add_argument("--prior", nargs="*", default=None,
                        help="prior date CSVs to check for overlaps "
                             "(default: auto-discover jobs_*.csv / jobs_output_*.csv in this folder)")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="seconds to wait between page fetches (default 1.5)")
    args = parser.parse_args()

    _ensure_cache_dir()

    with open(args.input_csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
        if "requiredSkills" not in fieldnames or "sourceLink" not in fieldnames:
            sys.exit("[error] input CSV needs company/role/location/sourceLink/requiredSkills columns")

    print(f"Loaded {len(rows)} rows from {args.input_csv}")

    prior_paths = discover_prior_csvs(args.input_csv, args.output_csv, args.prior)
    prior_urls, prior_composites = load_prior_keys(prior_paths)
    print(f"Prior overlap sources: {len(prior_paths)} file(s) -> "
          f"{len(prior_urls)} URLs, {len(prior_composites)} company+role+location keys")

    # --- Pass 1: remove overlaps (URL first, then company+role+location) ---
    kept, removed = [], []
    for row in rows:
        if is_overlap(row, prior_urls, prior_composites):
            removed.append(row)
        else:
            kept.append(row)
    print(f"Overlaps removed: {len(removed)} (kept {len(kept)})")

    # --- Pass 2: refill empty requiredSkills from live pages ---
    session = fetch_session()
    missing = [row for row in kept if not str(row.get("requiredSkills") or "").strip()]
    print(f"Rows with empty requiredSkills to refill: {len(missing)}")

    filled, still_empty = 0, 0
    for i, row in enumerate(missing, 1):
        url = (row.get("sourceLink") or "").strip()
        skills = ""
        if url:
            try:
                skills = skills_from_url(url, session)
            except Exception as e:
                print(f"  [{i}/{len(missing)}] fetch error for {url[:70]}: {type(e).__name__}: {e}")
        if skills:
            row["requiredSkills"] = skills
            filled += 1
        else:
            still_empty += 1
        if i % 25 == 0:
            print(f"  ... {i}/{len(missing)} processed "
                  f"({filled} filled, {still_empty} still empty)")
        time.sleep(max(args.delay, 0))

    # Fallback pass: rows whose pages could not be fetched or whose fetched text
    # names no taxonomy skill are left with an empty requiredSkills cell. We do
    # not invent hardcoded values from the role title — skills must come from
    # the posting's real text.
    still_empty = sum(1 for row in kept if not str(row.get("requiredSkills") or "").strip())

    # --- Pass 3: write output ---
    print(f"Skill refill complete: {filled} filled, {still_empty} still empty")
    print(f"Writing {len(kept)} rows to {args.output_csv}")

    with open(args.output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames,
                                quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(kept)

    overlap_path = args.output_csv.rsplit(".csv", 1)[0] + "_overlaps_removed.csv"
    if removed:
        with open(overlap_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames,
                                    quoting=csv.QUOTE_ALL, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(removed)
        print(f"Removed overlap detail written to {overlap_path}")

    print("Done.")


if __name__ == "__main__":
    main()
