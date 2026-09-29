"""
clean_html_descriptions.py
==========================
Strips any residual HTML tags from the `description` field of a scraped
jobs CSV and writes a cleaned copy.

Usage:
    python3 clean_html_descriptions.py <input_csv> <output_csv>

Example:
    python3 clean_html_descriptions.py jobs_2026-09-11.csv jobs_2026-09-11_clean.csv
"""

import csv
import re
import sys
csv.field_size_limit(sys.maxsize)
import unicodedata
from html import unescape as html_unescape

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("[warn] beautifulsoup4 not installed — falling back to regex-based HTML stripping")


def strip_html(text):
    """Remove HTML tags and normalize whitespace from a string."""
    if not text:
        return ""
    # Use BeautifulSoup for proper HTML parsing if available
    if BS4_AVAILABLE and ("<" in text and ">" in text):
        text = BeautifulSoup(text, "html.parser").get_text("\n")
    else:
        # Fallback: regex strip tags
        text = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities (&amp; &lt; etc.)
    text = html_unescape(text)
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Strip control/zero-width characters
    text = "".join(
        ch for ch in text
        if ch in ("\n", "\t") or unicodedata.category(ch)[0] != "C"
    )
    # Collapse multiple spaces/tabs on a line
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def clean_csv(input_path, output_path):
    cleaned = 0
    total = 0

    with open(input_path, encoding="utf-8-sig", newline="") as fin, \
         open(output_path, "w", encoding="utf-8-sig", newline="") as fout:

        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames

        if "description" not in fieldnames:
            print(f"[error] No 'description' column found in {input_path}")
            sys.exit(1)

        writer = csv.DictWriter(
            fout, fieldnames=fieldnames,
            quoting=csv.QUOTE_ALL,
            lineterminator="\r\n",
        )
        writer.writeheader()

        for row in reader:
            total += 1
            original = row.get("description", "")
            cleaned_desc = strip_html(original)

            if cleaned_desc != original:
                cleaned += 1

            row["description"] = cleaned_desc
            writer.writerow(row)

    print(f"Done. {total} rows processed, {cleaned} description(s) had HTML stripped.")
    print(f"Clean file written to: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 clean_html_descriptions.py <input_csv> <output_csv>")
        sys.exit(1)

    clean_csv(sys.argv[1], sys.argv[2])
