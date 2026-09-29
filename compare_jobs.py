#!/usr/bin/env python3
"""
Compare job postings across different dates to identify overlaps and duplicates.
Analyzes based on company, location, job title, and URL.
"""

import pandas as pd
import os
from pathlib import Path

def load_job_files():
    """Load all dated job output files."""
    files = {
        '2026-09-07': 'jobs_output_2026-09-07.csv',
        '2026-09-08': 'jobs_output_2026-09-08.csv',
        '2026-09-09': 'jobs_output_2026-09-09.csv',
        '2026-09-10': 'jobs_2026-09-10.csv',
    }
    
    data = {}
    for date, filename in files.items():
        filepath = Path(filename)
        if filepath.exists():
            df = pd.read_csv(filepath)
            data[date] = df
            print(f"Loaded {date}: {len(df)} jobs")
        else:
            print(f"File not found: {filename}")
    
    return data

def analyze_overlaps(data):
    """Analyze overlaps across dates."""
    dates = sorted(data.keys())
    
    print("\n" + "="*80)
    print("OVERLAP ANALYSIS")
    print("="*80)
    
    # Create a key for each job (company + location + role)
    for date in dates:
        df = data[date]
        # Create a normalized key for matching
        df['key'] = (df['company'].str.lower().str.strip() + '|' + 
                     df['location'].str.lower().str.strip() + '|' + 
                     df['role'].str.lower().str.strip())
        df['url_key'] = df['sourceLink'].str.lower().str.strip()
    
    # Compare each date with the next
    comparison_results = {}
    
    for i in range(len(dates) - 1):
        curr_date = dates[i]
        next_date = dates[i + 1]
        
        curr_df = data[curr_date]
        next_df = data[next_date]
        
        # Find overlaps by key (company + location + role)
        overlaps_by_key = set(curr_df['key']) & set(next_df['key'])
        
        # Find overlaps by URL
        overlaps_by_url = set(curr_df['url_key']) & set(next_df['url_key'])
        
        # Find jobs only in current date
        only_in_curr = set(curr_df['key']) - set(next_df['key'])
        
        # Find jobs only in next date
        only_in_next = set(next_df['key']) - set(curr_df['key'])
        
        comparison_results[f"{curr_date}_to_{next_date}"] = {
            'overlaps_by_key': overlaps_by_key,
            'overlaps_by_url': overlaps_by_url,
            'only_in_curr': only_in_curr,
            'only_in_next': only_in_next,
            'curr_total': len(curr_df),
            'next_total': len(next_df),
        }
        
        print(f"\n{curr_date} → {next_date}")
        print(f"  {curr_date} total: {len(curr_df)}")
        print(f"  {next_date} total: {len(next_df)}")
        print(f"  Overlap by key (company+location+role): {len(overlaps_by_key)}")
        print(f"  Overlap by URL: {len(overlaps_by_url)}")
        print(f"  New in {curr_date}: {len(only_in_curr)}")
        print(f"  New in {next_date}: {len(only_in_next)}")
    
    return comparison_results, data

def show_overlap_details(data, comparison_results):
    """Show detailed overlap information."""
    dates = sorted(data.keys())
    
    print("\n" + "="*80)
    print("DETAILED OVERLAP INFORMATION (Sep 09 → Sep 10)")
    print("="*80)
    
    comparison_key = f"{dates[-2]}_to_{dates[-1]}"
    result = comparison_results[comparison_key]
    
    curr_date = dates[-2]
    next_date = dates[-1]
    curr_df = data[curr_date]
    next_df = data[next_date]
    
    # Show jobs appearing in both dates (by key)
    overlapping_keys = result['overlaps_by_key']
    print(f"\nJobs appearing in both {curr_date} and {next_date} ({len(overlapping_keys)}):")
    print("-" * 80)
    
    overlap_details = []
    for key in sorted(overlapping_keys)[:20]:  # Show first 20
        curr_matches = curr_df[curr_df['key'] == key]
        next_matches = next_df[next_df['key'] == key]
        
        for _, row in curr_matches.iterrows():
            overlap_details.append({
                'date': curr_date,
                'company': row['company'],
                'location': row['location'],
                'role': row['role'],
                'url': row['sourceLink'],
                'platform': row['platform']
            })
    
    overlap_df = pd.DataFrame(overlap_details)
    print(overlap_df.to_string(index=False))
    
    if len(overlapping_keys) > 20:
        print(f"\n... and {len(overlapping_keys) - 20} more overlapping jobs")
    
    # Show new jobs in latest date
    print(f"\n\nNew jobs in {next_date} (not in {curr_date}):")
    print("-" * 80)
    
    new_keys = result['only_in_next']
    new_in_next = next_df[next_df['key'].isin(new_keys)][['company', 'location', 'role', 'sourceLink', 'platform']]
    
    print(f"Total new jobs: {len(new_in_next)}\n")
    print(new_in_next.head(15).to_string(index=False))
    
    if len(new_in_next) > 15:
        print(f"\n... and {len(new_in_next) - 15} more new jobs")
    
    # Show removed jobs
    print(f"\n\nJobs removed/not in {next_date} (were in {curr_date}):")
    print("-" * 80)
    
    removed_keys = result['only_in_curr']
    removed = curr_df[curr_df['key'].isin(removed_keys)][['company', 'location', 'role', 'sourceLink', 'platform']]
    
    print(f"Total removed: {len(removed)}\n")
    print(removed.head(15).to_string(index=False))
    
    if len(removed) > 15:
        print(f"\n... and {len(removed) - 15} more removed jobs")

def export_overlap_summary(data, comparison_results):
    """Export overlap summary to CSV."""
    dates = sorted(data.keys())
    
    summary_data = []
    for comp_key, result in sorted(comparison_results.items()):
        dates_pair = comp_key.split('_to_')
        summary_data.append({
            'comparison': comp_key,
            'date1': dates_pair[0],
            'date2': dates_pair[1],
            'total_in_date1': result['curr_total'],
            'total_in_date2': result['next_total'],
            'overlaps_by_key': len(result['overlaps_by_key']),
            'overlaps_by_url': len(result['overlaps_by_url']),
            'new_in_date1': len(result['only_in_curr']),
            'new_in_date2': len(result['only_in_next']),
        })
    
    summary_df = pd.DataFrame(summary_data)
    summary_df.to_csv('job_overlap_summary.csv', index=False)
    print("\n✓ Overlap summary saved to job_overlap_summary.csv")

if __name__ == "__main__":
    data = load_job_files()
    
    if not data:
        print("No job files found!")
        exit(1)
    
    comparison_results, data = analyze_overlaps(data)
    show_overlap_details(data, comparison_results)
    export_overlap_summary(data, comparison_results)
