#!/usr/bin/env python3
"""Fix jobs_2026-09-28.csv:
   1. collapse multi-location cells to a single location
   2. drop rows whose company+role+location already appear in an earlier date's CSV
"""
import csv, glob, os, re, shutil, sys
import job_scraper as js

TARGET = "jobs_2026-09-28.csv"
COLS = ['company','role','platform','location','remote','salaryMin','salaryMax',
        'seniority','visaSponsorship','employmentType','description',
        'requiredSkills','tags','sourceLink','active']

WORKMODE = re.compile(r"\s*[-–—]\s*(?:remote|hybrid|on-?site|onsite)\s*$", re.I)
SPLIT = re.compile(r"\s*(?:;|\s\|\s|\s/\s|,\s*or\s+|\s+or\s+)\s*", re.I)


def single_location(val):
    s = js.one_line(str(val or "")).strip()
    s = WORKMODE.sub("", s).strip()
    parts = [p.strip(" ,") for p in SPLIT.split(s) if p.strip(" ,")]
    parts = [re.sub(r"\s+within\s+\w[\w\s]*$", "", p, flags=re.I).strip() for p in parts]
    parts = [p for p in parts if p]
    return parts[0] if parts else ("" if not s else "Remote")


def key(r):
    return (js.one_line(r.get("company") or "").strip().lower(),
            js.one_line(r.get("role") or "").strip().lower(),
            js.one_line(r.get("location") or "").strip().lower())


def rows(p):
    with open(p, newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


others = sorted(p for p in glob.glob("*.csv")
                if p != TARGET and not os.path.basename(p).startswith(".~lock")
                and not p.startswith(("new_in_", "jobs_output_deduped", "sample"))
                and os.path.getsize(p) > 0)
ref_key = {}
for p in others:
    try:
        for r in rows(p):
            k = key(r)
            if all(k):
                ref_key.setdefault(k, p)
    except Exception as e:
        print("skip", p, e)

tgt = rows(TARGET)
shutil.copy2(TARGET, TARGET + ".bak")

out, seen, n_loc, n_drop = [], set(), 0, 0
for r in tgt:
    fixed = single_location(r.get("location"))
    if fixed != (r.get("location") or "").strip():
        r["location"] = fixed
        n_loc += 1
    k = key(r)
    if all(k):
        if k in ref_key:
            print(f"  DROP row (dup of {ref_key[k]}): {r['company']} | {r['role']} | {r['location']}")
            n_drop += 1
            continue
        if k in seen:
            print(f"  DROP row (internal dup): {r['company']} | {r['role']} | {r['location']}")
            n_drop += 1
            continue
        seen.add(k)
    out.append(r)

with open(TARGET, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLS, quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(out)

print(f"\nlocations fixed: {n_loc}")
print(f"rows dropped   : {n_drop}")
print(f"rows in        : {len(tgt)} -> {len(out)}")
