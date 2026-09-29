#!/usr/bin/env python3
"""
Validates jobs CSV against specific data quality conditions:
1. Fully fetched descriptions (no truncation)
2. No hardcoded required skills
3. Removes inactive/broken URLs
4. No job expiration dates
5. Deduplication check
6. No multiple locations in location column
"""

import pandas as pd
import re
from urllib.parse import urlparse
from collections import defaultdict

def check_truncation_patterns(description):
    """Check if description appears truncated."""
    if pd.isna(description) or not isinstance(description, str):
        return False
    
    truncation_signs = [
        r'\.\.\.(\s|$)',  # ends with ...
        r'<truncated>',
        r'\[more\]',
        r'(read more|see more|click here)',
        r'(\|| •|\||More)(\s*)$'  # ends with More or pipe/bullet
    ]
    
    for pattern in truncation_signs:
        if re.search(pattern, description, re.IGNORECASE):
            return True
    return False

def check_description_completeness(description):
    """Check if description is long enough to be complete."""
    if pd.isna(description) or not isinstance(description, str):
        return False
    # Assume descriptions under 100 chars are likely truncated/incomplete
    return len(description.strip()) >= 100

def check_hardcoded_skills(skills):
    """Check if requiredSkills field is populated (should be empty)."""
    if pd.isna(skills) or skills == '':
        return False  # Good - no hardcoded skills
    return True  # Bad - has hardcoded skills

def check_url_validity(url):
    """Check if URL is valid."""
    if pd.isna(url) or not isinstance(url, str):
        return False
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def check_multiple_locations(location):
    """Check if location column contains multiple locations (comma-separated)."""
    if pd.isna(location) or not isinstance(location, str):
        return False
    
    # Check for common multi-location patterns
    location = location.strip()
    comma_count = location.count(',')
    
    # More than 2 commas likely indicates multiple locations
    # e.g., "City, State, City2, State2" 
    if comma_count > 1:
        return True
    
    # Check for "and", "or", "/" separators
    if re.search(r'\s+(and|or|\/)\s+', location, re.IGNORECASE):
        return True
    
    return False

def check_job_expiration(description):
    """Check if job posting includes expiration dates."""
    if pd.isna(description) or not isinstance(description, str):
        return False
    
    expiration_patterns = [
        r'deadline|opens|closes|closing.*\d{1,2}/\d{1,2}/\d{4}',
        r'applications? (close|due|deadline).*\d{1,2}/\d{1,2}',
        r'until\s+\d{1,2}/\d{1,2}/\d{4}',
        r'expires?.*\d{1,2}/\d{1,2}',
    ]
    
    for pattern in expiration_patterns:
        if re.search(pattern, description, re.IGNORECASE):
            return True
    return False

def main():
    file_path = '/home/vhits/Downloads/Job_scraper/jobs_2026-09-15.csv'
    
    print("Loading CSV file...")
    df = pd.read_csv(file_path)
    
    total_rows = len(df)
    print(f"Total jobs: {total_rows}\n")
    
    # Initialize violation counters
    violations = defaultdict(list)
    
    # Check each condition
    print("=" * 80)
    print("VALIDATION CHECKS")
    print("=" * 80)
    
    # 1. Check description completeness
    print("\n1. DESCRIPTION COMPLETENESS")
    print("-" * 80)
    truncated = 0
    incomplete = 0
    for idx, row in df.iterrows():
        desc = row['description']
        if check_truncation_patterns(desc):
            truncated += 1
            violations['truncated_descriptions'].append((idx, row['company'], row['role']))
        if not check_description_completeness(desc):
            incomplete += 1
            violations['incomplete_descriptions'].append((idx, row['company'], row['role']))
    
    print(f"✓ Truncated descriptions (ends with ...): {truncated}")
    print(f"✓ Incomplete descriptions (<100 chars): {incomplete}")
    if truncated > 0:
        print(f"  Sample truncated (first 3): {violations['truncated_descriptions'][:3]}")
    if incomplete > 0:
        print(f"  Sample incomplete (first 3): {violations['incomplete_descriptions'][:3]}")
    
    # 2. Check hardcoded required skills
    print("\n2. HARDCODED REQUIRED SKILLS")
    print("-" * 80)
    with_skills = 0
    empty_skills = 0
    for idx, row in df.iterrows():
        if check_hardcoded_skills(row['requiredSkills']):
            with_skills += 1
            violations['hardcoded_skills'].append((idx, row['company'], row['requiredSkills'][:50]))
        else:
            empty_skills += 1
    
    print(f"✓ Jobs with hardcoded requiredSkills: {with_skills} ({with_skills/total_rows*100:.1f}%)")
    print(f"✓ Jobs without requiredSkills: {empty_skills} ({empty_skills/total_rows*100:.1f}%)")
    if with_skills > 0:
        print(f"  Should be: NO hardcoded skills (empty field)")
        print(f"  Sample violations (first 3): {violations['hardcoded_skills'][:3]}")
    
    # 3. Check inactive jobs & broken URLs
    print("\n3. INACTIVE JOBS & BROKEN URLS")
    print("-" * 80)
    inactive = 0
    broken_urls = 0
    for idx, row in df.iterrows():
        if row['active'] == False or str(row['active']).lower() == 'false':
            inactive += 1
            violations['inactive_jobs'].append((idx, row['company'], row['sourceLink']))
        
        if not check_url_validity(row['sourceLink']):
            broken_urls += 1
            violations['broken_urls'].append((idx, row['company'], row['sourceLink']))
    
    print(f"✓ Inactive jobs (active=false): {inactive}")
    print(f"✓ Broken/invalid URLs: {broken_urls}")
    if inactive > 0:
        print(f"  Sample inactive jobs (first 3): {violations['inactive_jobs'][:3]}")
    if broken_urls > 0:
        print(f"  Sample broken URLs (first 3): {violations['broken_urls'][:3]}")
    
    # 4. Check for job expiration mentions
    print("\n4. JOB EXPIRATION DATES IN DESCRIPTIONS")
    print("-" * 80)
    with_expiration = 0
    for idx, row in df.iterrows():
        if check_job_expiration(row['description']):
            with_expiration += 1
            violations['expiration_mentioned'].append((idx, row['company'], row['role']))
    
    print(f"✓ Jobs mentioning expiration/closing dates: {with_expiration} ({with_expiration/total_rows*100:.1f}%)")
    if with_expiration > 0:
        print(f"  Sample (first 3): {violations['expiration_mentioned'][:3]}")
    
    # 5. Check for multiple locations
    print("\n5. MULTIPLE LOCATIONS IN LOCATION COLUMN")
    print("-" * 80)
    multi_loc = 0
    for idx, row in df.iterrows():
        if check_multiple_locations(row['location']):
            multi_loc += 1
            violations['multiple_locations'].append((idx, row['company'], row['location']))
    
    print(f"✓ Jobs with multiple locations: {multi_loc} ({multi_loc/total_rows*100:.1f}%)")
    if multi_loc > 0:
        print(f"  Sample multi-location entries (first 5):")
        for v in violations['multiple_locations'][:5]:
            print(f"    - {v[2]}")
    
    # 6. Deduplication check (within same file)
    print("\n6. DEDUPLICATION CHECK (WITHIN FILE)")
    print("-" * 80)
    
    # Check for exact duplicates on key fields
    dedup_cols = ['company', 'role', 'location', 'sourceLink']
    duplicates = df.duplicated(subset=dedup_cols, keep=False)
    dup_count = duplicates.sum() // 2  # Each pair counted twice
    
    print(f"✓ Exact duplicates (company+role+location+url): {dup_count}")
    if duplicates.any():
        print(f"  Total rows with duplicates: {duplicates.sum()}")
        print(f"  Sample duplicate pairs:")
        dup_df = df[duplicates].sort_values(by=dedup_cols)
        for i, (idx, row) in enumerate(dup_df.iterrows()):
            if i >= 3:
                break
            print(f"    - {row['company']} | {row['role']} | {row['location']}")
    
    # 7. Summary Report
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    total_violations = sum(len(v) for v in violations.values())
    print(f"\nTotal potential data quality issues: {total_violations}")
    
    print("\nRECOMMENDATIONS:")
    print("-" * 80)
    if with_skills > 0:
        print(f"⚠️  CRITICAL: Remove or clear all {with_skills} hardcoded 'requiredSkills' entries")
    if inactive > 0:
        print(f"⚠️  CRITICAL: Remove {inactive} inactive jobs (active=false)")
    if broken_urls > 0:
        print(f"⚠️  CRITICAL: Investigate/remove {broken_urls} broken URLs")
    if multi_loc > 0:
        print(f"⚠️  WARNING: Split {multi_loc} jobs with multiple locations into separate rows")
    if with_expiration > 0:
        print(f"⚠️  WARNING: Review {with_expiration} jobs mentioning expiration dates")
    if truncated > 0:
        print(f"⚠️  WARNING: Verify {truncated} potentially truncated descriptions")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    main()
