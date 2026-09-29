#!/usr/bin/env python3
"""Drop rows from jobs_2026-09-28.csv whose sourceLink is confirmed dead."""
import csv, shutil

TARGET = "jobs_2026-09-28.csv"
COLS = ['company','role','platform','location','remote','salaryMin','salaryMax',
        'seniority','visaSponsorship','employmentType','description',
        'requiredSkills','tags','sourceLink','active']

DEAD = [
    "https://jooble.org/away/-1668560835440103945?p=1&pos=7&rgn=0&cid=19344&ckey=NONE&jobAge=95&relb=152&brelb=110&scr=151.1239687272727&bscr=109.36603&aq=8535487829975998217&elckey=2352562711060605221",
    "https://jooble.org/away/-3950138427854936099?p=1&pos=10&rgn=0&cid=19344&ckey=NONE&jobAge=143&relb=145&brelb=110&scr=143.50624954545455&bscr=108.86681&aq=8535487829975998217&elckey=2352562711060605221",
    "https://jooble.org/away/-6747610857074375977?p=1&pos=20&rgn=0&cid=19344&ckey=NONE&jobAge=143&relb=134&brelb=110&scr=132.93822653636362&bscr=109.128395&aq=8535487829975998217&elckey=2352562711060605221",
]

shutil.copy2(TARGET, TARGET + ".bak2")
with open(TARGET, newline="", encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))

dead_set = set(DEAD)
kept, dropped = [], []
for r in rows:
    u = (r.get("sourceLink") or "").strip()
    if u in dead_set:
        dropped.append((r["company"], r["role"], r["location"]))
    else:
        kept.append(r)

with open(TARGET, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=COLS, quoting=csv.QUOTE_ALL)
    w.writeheader()
    w.writerows(kept)

print("dropped:")
for d in dropped:
    print("  ", d)
print(f"\nrows: {len(rows)} -> {len(kept)}  (backup: {TARGET}.bak2)")
