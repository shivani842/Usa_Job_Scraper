#!/usr/bin/env python3
"""
Test URL validation for inactive/broken source links.

This script tests the URL validation functionality to ensure it correctly
identifies and skips inactive, broken, or tracking URLs.
"""

import sys
from job_scraper import is_source_link_active, should_skip_url, SKIP_URL_RE


def test_skip_patterns():
    """Test the URL pattern matching for known tracking/broken URLs."""
    print("Testing URL skip patterns...")
    
    # Test URLs that should be skipped
    test_skip_urls = [
        "https://jobviewtrack.com/abc123",
        "https://indeed.com/viewjob?jk=abc&trk=homepage",
        "https://linkedin.com/jobs/view/12345?trk=jobsearch",
        "https://example.com/track/apply/123",
        "https://jobviewtrack.example.com/job/123",
        "https://adzuna.com/land/ad/5883289931?se=bJS4hAWw8RG-FLx_YfIXKQ&utm_medium=api",
        "https://jooble.org/desc/4835502559392319386?ckey=NONE&rgn=0&pos=4",
    ]
    
    for url in test_skip_urls:
        if should_skip_url(url):
            print(f"  [OK] Correctly skipping: {url[:60]}...")
        else:
            print(f"  [FAIL] Should have skipped: {url[:60]}...")
    
    # Test URLs that should NOT be skipped (pattern-only check)
    test_pattern_keep_urls = [
        "https://example.com/jobs/123",
        "https://company.com/careers/software-engineer",
        "https://boards.greenhouse.io/company/jobs/12345",
        "https://www.usajobs.gov/job/123456",
    ]
    
    for url in test_pattern_keep_urls:
        if not SKIP_URL_RE.search(url):
            print(f"  [OK] Correctly keeping (pattern): {url[:60]}...")
        else:
            print(f"  [FAIL] Should not have skipped (pattern): {url[:60]}...")
    
    print("Pattern tests completed.\n")


def test_url_regex():
    """Test the compiled URL regex pattern."""
    print("Testing URL regex pattern...")
    
    test_cases = [
        ("jobviewtrack", True),
        ("indeed.qld", True),
        ("/track/apply", True),
        ("?trk=abc", True),
        ("adzuna.com/land/", True),
        ("jooble.org/desc/123?ckey=abc", True),
        ("normal-url", False),
        ("company.com/jobs", False),
        ("usajobs.gov/job/123", False),
    ]
    
    for pattern, should_match in test_cases:
        matches = bool(SKIP_URL_RE.search(pattern))
        if matches == should_match:
            status = "OK"
        else:
            status = "FAIL"
        print(f"  [{status}] Pattern '{pattern}' {'matches' if matches else 'no match'} (expected {'match' if should_match else 'no match'})")
    
    print("Regex tests completed.\n")


if __name__ == "__main__":
    print("URL Validation Tests\n" + "="*50 + "\n")
    
    test_skip_patterns()
    test_url_regex()
    
    print("All tests completed.")
    print("\nNote: Pattern matching tests validate URL filtering logic.")
    print("is_source_link_active() requires network access to test real URLs.")
    print("Run the main scraper to test with actual job posting URLs.")
