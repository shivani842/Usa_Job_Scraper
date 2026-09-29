#!/usr/bin/env python3
import csv, glob, os, re, sys, json
from concurrent.futures import ThreadPoolExecutor

import job_scraper as js

TARGET = "jobs_2026-09-28.csv"
COLS = ['company','role','platform','location','remote','salaryMin','salaryMax',
        'seniority','visaSponsorship','employmentType','description',
        'requiredSkills','tags','sourceLink','active']


def rows(path):
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def norm_url(v):
    return js._norm_url(str(v or "").strip())


def key(r):
    return (js.one_line(r.get("company") or "").strip().lower(),
            js.one_line(r.get("role") or "").strip().lower(),
            js.normalize_location(r.get("location") or "").strip().lower())


def multi_loc(v):
    s = js.one_line(str(v or "")).strip()
    if not s:
        return False
    if re.search(r"\s*(?:;|\s\|\s|\s/\s)\s*", s):
        return True
    if re.search(r"\s+(?:and|or)\s+", s, re.I):
        return True
    if re.search(r"\s-\s(remote|hybrid|on-?site)\b", s, re.I):
        return True
    return False


tgt = rows(TARGET)
others = sorted(p for p in glob.glob("*.csv")
                if p != TARGET and not os.path.basename(p).startswith(".~lock")
                and not p.startswith(("new_in_", "jobs_output_deduped", "sample"))
                and os.path.getsize(p) > 0)

ref_url, ref_key, ref_url_src = {}, {}, {}
for p in others:
    try:
        for r in rows(p):
            u = norm_url(r.get("sourceLink") or r.get("url") or "")
            if u:
                ref_url.setdefault(u, p)
            k = key(r)
            if all(k):
                ref_key.setdefault(k, p)
    except Exception as e:
        print("skip", p, e)

print(f"TARGET {TARGET}: {len(tgt)} rows")
print(f"Reference files scanned: {len(others)}\n")

# 1. fully empty rows
empty_rows = [i for i, r in enumerate(tgt)
              if all(str(v or "").strip() == "" for v in r.values())]

# 2. empty fields per column
empty_cols = {c: [i for i, r in enumerate(tgt) if str(r.get(c) or "").strip() == ""]
              for c in COLS}
empty_cols = {c: v for c, v in empty_cols.items() if v}

# 3. multi-location
multi = [(i, tgt[i]["location"]) for i in range(len(tgt)) if multi_loc(tgt[i]["location"])]

# 4. overlap url / key
ov_url, ov_key = [], []
for i, r in enumerate(tgt):
    u = norm_url(r.get("sourceLink"))
    if u and u in ref_url:
        ov_url.append((i, u, ref_url[u]))
    k = key(r)
    if all(k) and k in ref_key:
        ov_key.append((i, k, ref_key[k]))

# 4b. internal duplicates
int_url = {}
for i, r in enumerate(tgt):
    int_url.setdefault(norm_url(r["sourceLink"]), []).append(i)
int_url = {k: v for k, v in int_url.items() if len(v) > 1}
int_key = {}
for i, r in enumerate(tgt):
    int_key.setdefault(key(r), []).append(i)
int_key = {k: v for k, v in int_key.items() if len(v) > 1}

# 4c. same company+role+location but different url
pair = {}
for i, r in enumerate(tgt):
    pair.setdefault(key(r), set()).add(norm_url(r["sourceLink"]))
multi_url_same_job = {k: v for k, v in pair.items() if len(v) > 1}

# 5. bad url format
bad_url = [(i, tgt[i]["sourceLink"][:120]) for i in range(len(tgt))
           if not str(tgt[i].get("sourceLink") or "").strip().startswith(("http://", "https://"))]

# 6. inactive flag column
inactive_flag = [i for i in range(len(tgt))
                 if str(tgt[i].get("active") or "").strip().lower() in ("false", "0", "no")]

print("=" * 70)
print(f"1. Fully empty rows           : {len(empty_rows)} {empty_rows[:10]}")
print(f"2. Rows with empty field(s)   : {len(empty_cols)}")
for c, v in sorted(empty_cols.items(), key=lambda x: -len(x[1])):
    print(f"     - {c}: {len(v)} rows  e.g. idx {v[:5]}")
print(f"3. Multi-location cells       : {len(multi)}")
for i, v in multi[:10]:
    print(f"     - row {i}: {v}")
print(f"4a. URL overlaps w/ other dates: {len(ov_url)}")
for i, u, p in ov_url[:10]:
    print(f"     - row {i} {u}  <= {p}")
print(f"4b. company+role+location overlap: {len(ov_key)}")
for i, k, p in ov_key[:10]:
    print(f"     - row {i} {k}  <= {p}")
print(f"4c. Internal dup URLs         : {len(int_url)}")
for k, v in list(int_url.items())[:10]:
    print(f"     - {k} rows {v}")
print(f"4d. Internal dup keys         : {len(int_key)}")
for k, v in list(int_key.items())[:10]:
    print(f"     - {k} rows {v}")
print(f"4e. Same key, >1 URL          : {len(multi_url_same_job)}")
for k, v in list(multi_url_same_job.items())[:10]:
    print(f"     - {k} -> {len(v)} urls")
print(f"5. Malformed URLs             : {len(bad_url)}")
for i, u in bad_url[:10]:
    print(f"     - row {i}: {u}")
print(f"6. active==false rows         : {len(inactive_flag)} {inactive_flag[:10]}")
print("=" * 70)

if "--live" in sys.argv:
    urls = sorted({str(r["sourceLink"]).strip() for r in tgt if str(r.get("sourceLink") or "").strip()})
    print(f"\nChecking {len(urls)} unique URLs for activity ...")
    dead = []
    with ThreadPoolExecutor(max_workers=24) as ex:
        for u, ok in zip(urls, ex.map(js.is_source_link_active, urls)):
            if not ok:
                dead.append(u)
    print(f"7. Inactive/broken URLs       : {len(dead)}")
    for u in dead[:40]:
        print("     -", u)
    idx = {u: i for i, u in enumerate(tgt)}
    with open("dead_urls_28.txt", "w") as f:
        for u in dead:
            f.write(f"{u}\n")
