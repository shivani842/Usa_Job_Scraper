#!/usr/bin/env python3
"""
Detailed export of overlapping jobs across dates.
"""

import pandas as pd
from pathlib import Path

def create_detailed_overlap_report():
    """Create detailed reports of overlapping jobs."""
    
    # Load files
    files = {
        '2026-09-07': 'jobs_output_2026-09-07.csv',
        '2026-09-08': 'jobs_output_2026-09-08.csv',
        '2026-09-09': 'jobs_output_2026-09-09.csv',
        '2026-09-10': 'jobs_2026-09-10.csv',
    }
    
    data = {}
    for date, filename in files.items():
        if Path(filename).exists():
            df = pd.read_csv(filename)
            df['key'] = (df['company'].str.lower().str.strip() + '|' + 
                        df['location'].str.lower().str.strip() + '|' + 
                        df['role'].str.lower().str.strip())
            data[date] = df
    
    dates = sorted(data.keys())
    
    # Focus on Sep 09 → Sep 10 comparison
    curr_date = dates[-2]  # 2026-09-09
    next_date = dates[-1]  # 2026-09-10
    
    curr_df = data[curr_date]
    next_df = data[next_date]
    
    # Find overlaps by key
    overlapping_keys = set(curr_df['key']) & set(next_df['key'])
    
    # Get overlapping jobs details
    overlaps_list = []
    for key in overlapping_keys:
        curr_jobs = curr_df[curr_df['key'] == key]
        next_jobs = next_df[next_df['key'] == key]
        
        for _, curr_row in curr_jobs.iterrows():
            for _, next_row in next_jobs.iterrows():
                overlaps_list.append({
                    'company': curr_row['company'],
                    'location': curr_row['location'],
                    'role': curr_row['role'],
                    'url_sep_09': curr_row['sourceLink'],
                    'platform': curr_row['platform'],
                    'url_sep_10': next_row['sourceLink'],
                    'same_url': 1 if curr_row['sourceLink'].lower() == next_row['sourceLink'].lower() else 0,
                })
    
    overlaps_df = pd.DataFrame(overlaps_list)
    overlaps_df.to_csv('overlapping_jobs_sep09_sep10.csv', index=False)
    print(f"✓ Detailed overlaps saved: overlapping_jobs_sep09_sep10.csv ({len(overlaps_df)} rows)")
    
    # Create pivot summary
    print("\nOVERLAP SUMMARY - Sep 09 to Sep 10:")
    print(f"  Total jobs in Sep 09: {len(curr_df)}")
    print(f"  Total jobs in Sep 10: {len(next_df)}")
    print(f"  Overlapping (same company/location/role): {len(overlaps_df)}")
    print(f"  With exact same URL: {overlaps_df['same_url'].sum()}")
    
    # Create comparison across all dates
    all_dates = sorted(data.keys())
    timeline_summary = []
    
    for date in all_dates:
        timeline_summary.append({
            'date': date,
            'total_jobs': len(data[date]),
        })
    
    timeline_df = pd.DataFrame(timeline_summary)
    timeline_df.to_csv('jobs_timeline_summary.csv', index=False)
    print(f"\n✓ Timeline summary saved: jobs_timeline_summary.csv")
    print(timeline_df.to_string(index=False))

if __name__ == "__main__":
    create_detailed_overlap_report()
