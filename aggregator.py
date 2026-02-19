import os
import json
from datetime import datetime

def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

# Directory where the JSON files are stored
data_dir = "data"

# Get all _cleaned.json files
files = [f for f in os.listdir(data_dir) if f.endswith('_cleaned.json') and f.startswith('allied_')]

# Parse dates and sort files by date
dated_files = []
for f in files:
    try:
        date_str = f.split('_')[1]  # Assuming format YYYY-MM-DD_cleaned.json
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        dated_files.append((date, f))
    except ValueError:
        log(f"Invalid date in file: {f}")
dated_files.sort(key=lambda x: x[0])  # Sort by date

# Load data for each file
data_by_date = {}
for date, file in dated_files:
    path = os.path.join(data_dir, file)
    with open(path, 'r', encoding='utf-8') as f:
        data_by_date[date] = json.load(f)

# Get sorted dates
sorted_dates = sorted(data_by_date.keys())

# Compare consecutive days
for i in range(1, len(sorted_dates)):
    prev_date = sorted_dates[i-1]
    curr_date = sorted_dates[i]
    prev_data = data_by_date[prev_date]
    curr_data = data_by_date[curr_date]

    log(f"Comparing {prev_date} to {curr_date}")

    prev_properties = {p['name']: p for p in prev_data.get('properties', [])}
    curr_properties = {p['name']: p for p in curr_data.get('properties', [])}

    all_property_names = set(prev_properties.keys()) | set(curr_properties.keys())

    total_added_sqft = 0
    total_removed_sqft = 0

    for prop_name in sorted(all_property_names):
        prev_suites = prev_properties.get(prop_name, {}).get('suites', [])
        curr_suites = curr_properties.get(prop_name, {}).get('suites', [])

        prev_suite_numbers = {s['suite_number'] for s in prev_suites}
        curr_suite_numbers = {s['suite_number'] for s in curr_suites}

        added = curr_suite_numbers - prev_suite_numbers
        removed = prev_suite_numbers - curr_suite_numbers

        if added:
            for suite in sorted(added):
                suite_data = next(s for s in curr_suites if s['suite_number'] == suite)
                sqft = suite_data['sq_ft']
                total_added_sqft += sqft
                print(f"{prop_name} suite {suite} added ({sqft} sq ft)")
        if removed:
            for suite in sorted(removed):
                suite_data = next(s for s in prev_suites if s['suite_number'] == suite)
                sqft = suite_data['sq_ft']
                total_removed_sqft += sqft
                print(f"{prop_name} suite {suite} removed ({sqft} sq ft)")

    net_change = total_removed_sqft - total_added_sqft
    log(f"Net square footage change: {net_change} sq ft (positive indicates net leased)")