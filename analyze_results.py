#!/usr/bin/env python3
"""
Analyze results.csv and print statistics about OEIS matches.

Deduplicates matches by line content to avoid counting vendored/copied code
multiple times.
"""

import csv
import os
from collections import Counter, defaultdict

# Increase CSV field size limit for large content fields
csv.field_size_limit(10 * 1024 * 1024)  # 10MB


def extract_oeis_number(matched_string):
    """Extract the numeric part after 'A' from oeis.org/AXXXXXX format."""
    if '/A' in matched_string:
        # Extract everything after '/A'
        num_str = matched_string.split('/A')[1]
        try:
            return int(num_str)
        except ValueError:
            return None
    return None


def print_match_details(unique_lines_list, max_display=10):
    """Print details of unique line matches with limit.

    Args:
        unique_lines_list: List of (line_content, [details]) tuples
        max_display: Maximum number of unique lines to display
    """
    total = len(unique_lines_list)
    displayed = min(total, max_display)

    for i, (line_content, locations) in enumerate(unique_lines_list[:max_display], 1):
        # Show the first location where this line appears
        first_location = locations[0]
        content = line_content
        if len(content) > 100:
            content = content[:97] + "..."

        print(f"**[{i}]** Content:")
        print(f"```")
        print(f"{content}")
        print(f"```")
        print(f"- Found in **{len(locations)}** location(s)")
        print(f"- Example: `{first_location['repository']}`")
        print(f"  - `{first_location['file_path']}:{first_location['line_number']}`")
        print()

    if total > displayed:
        print(f"*... and {total - displayed} more unique line(s)*")
        print()


def get_top_n_from_distinct_repos(oeis_list, n=20):
    """Get top N highest OEIS numbers from distinct repositories."""
    # Sort by OEIS number descending
    sorted_list = sorted(oeis_list, key=lambda x: x[0], reverse=True)

    # Filter to keep only one per repository
    seen_repos = set()
    result = []
    for oeis_num, matched_string, detail in sorted_list:
        repo = detail['repository']
        if repo not in seen_repos:
            seen_repos.add(repo)
            result.append((oeis_num, matched_string, detail))
            if len(result) >= n:
                break

    return result


def print_highest_matches(highest_list):
    """Print list of highest OEIS matches."""
    for i, (oeis_num, matched_string, detail) in enumerate(highest_list, 1):
        print(f"**[{i}]** [{matched_string}]({matched_string}) (A{oeis_num:06d})")
        print(f"- Repository: `{detail['repository']}`")
        print(f"- File: `{detail['file_path']}`")
        print(f"- Line: `{detail['line_number']}`")
        content = detail['line_content']
        if len(content) > 100:
            content = content[:97] + "..."
        print(f"- Content:")
        print(f"  ```")
        print(f"  {content}")
        print(f"  ```")
        print()


def main():
    # Read skip files
    repos_to_skip = set()
    with open('repos_to_skip.txt', 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                repos_to_skip.add(line)

    # Read CSV and collect data
    # Key change: deduplicate by line_content
    # matched_string -> line_content -> [details]
    all_matches_by_content = defaultdict(lambda: defaultdict(list))
    filtered_matches_by_content = defaultdict(lambda: defaultdict(list))
    all_oeis_with_numbers = []  # List of (oeis_num, matched_string, detail)
    filtered_oeis_with_numbers = []  # List of (oeis_num, matched_string, detail)

    # For raw statistics
    total_raw_matches = 0
    total_raw_filtered_matches = 0

    with open('results.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            matched_string = row['matched_string']
            repository = row['repository']
            file_path = row['file_path']
            line_content = row.get('line_content', '')

            total_raw_matches += 1

            detail = {
                'repository': repository,
                'file_path': file_path,
                'line_number': row.get('line_number', ''),
                'line_content': line_content,
            }

            # Collect for statistic 1 - deduplicated by line_content
            all_matches_by_content[matched_string][line_content].append(detail)

            # Collect for statistic 2 (highest A numbers)
            oeis_num = extract_oeis_number(matched_string)
            if oeis_num is not None:
                all_oeis_with_numbers.append((oeis_num, matched_string, detail))

            # Check for statistic 3 & 4 (filtered)
            # Skip if repository is in repos_to_skip
            if repository in repos_to_skip:
                continue

            total_raw_filtered_matches += 1

            # Collect for filtered stats - deduplicated by line_content
            filtered_matches_by_content[matched_string][line_content].append(detail)

            # Collect for highest OEIS numbers among filtered matches
            if oeis_num is not None:
                filtered_oeis_with_numbers.append((oeis_num, matched_string, detail))

    # Compute statistics based on unique line contents
    # Count how many unique line contents each matched_string has
    all_match_counts = {}
    for matched_string, contents in all_matches_by_content.items():
        all_match_counts[matched_string] = len(contents)  # Number of unique lines

    filtered_match_counts = {}
    for matched_string, contents in filtered_matches_by_content.items():
        filtered_match_counts[matched_string] = len(contents)  # Number of unique lines

    # Compute statistics
    print("# OEIS Results Statistics")
    print()
    print("*Deduplicated by line content*")
    print()
    print("---")
    print()

    # Statistic 1: Most common matched_string (by unique line contents)
    if all_match_counts:
        most_common_match = max(all_match_counts.items(), key=lambda x: x[1])
        matched_string, unique_count = most_common_match

        # Get the unique lines for this matched_string
        unique_lines = [(line, locs) for line, locs in all_matches_by_content[matched_string].items()]
        # Sort by number of locations (most copied first)
        unique_lines.sort(key=lambda x: len(x[1]), reverse=True)

        print(f"## 1. Most Common Matched String (All Matches)")
        print()
        print(f"**[{matched_string}]({matched_string})**")
        print()
        print(f"- **{unique_count}** distinct line(s) of code")
        print()
        print_match_details(unique_lines)

    # Statistic 2: Top 20 highest OEIS numbers from distinct repos
    if all_oeis_with_numbers:
        top_20 = get_top_n_from_distinct_repos(all_oeis_with_numbers, 20)
        print(f"## 2. Top 20 Highest OEIS Numbers")
        print()
        print("*One per distinct repository*")
        print()
        print_highest_matches(top_20)

    # Statistic 3: Most common filtered matched_string (by unique line contents)
    if filtered_match_counts:
        most_common_filtered = max(filtered_match_counts.items(), key=lambda x: x[1])
        matched_string, unique_count = most_common_filtered

        # Get the unique lines for this matched_string
        unique_lines = [(line, locs) for line, locs in filtered_matches_by_content[matched_string].items()]
        # Sort by number of locations (most copied first)
        unique_lines.sort(key=lambda x: len(x[1]), reverse=True)

        print(f"## 3. Most Common Matched String (Filtered)")
        print()
        print(f"*Excludes repos in repos_to_skip.txt*")
        print()
        print(f"**[{matched_string}]({matched_string})**")
        print()
        print(f"- **{unique_count}** distinct line(s) of code")
        print()
        print_match_details(unique_lines)

    # Statistic 4: Top 20 highest OEIS numbers (filtered) from distinct repos
    if filtered_oeis_with_numbers:
        top_20_filtered = get_top_n_from_distinct_repos(filtered_oeis_with_numbers, 20)
        print(f"## 4. Top 20 Highest OEIS Numbers (Filtered)")
        print()
        print("*Excludes repos in repos_to_skip.txt, one per distinct repository*")
        print()
        print_highest_matches(top_20_filtered)

    # Additional summary
    print("---")
    print()
    print("## Summary")
    print()

    # Count total unique (matched_string, line_content) pairs
    total_unique_uses = sum(len(contents) for contents in all_matches_by_content.values())
    total_unique_uses_filtered = sum(len(contents) for contents in filtered_matches_by_content.values())

    print("### Raw Matches")
    print()
    print(f"- Total raw matches in CSV: **{total_raw_matches}**")
    print(f"- Total raw matches after filtering: **{total_raw_filtered_matches}**")
    print()
    print("### After Deduplication by Line Content")
    print()
    print(f"- Unique uses (matched_string + line combos): **{total_unique_uses}**")
    print(f"- Unique uses after filtering: **{total_unique_uses_filtered}**")
    print(f"- Unique OEIS sequences referenced: **{len(all_matches_by_content)}**")
    print(f"- Unique OEIS sequences (filtered): **{len(filtered_matches_by_content)}**")
    print()
    print(f"**Deduplication saved counting {total_raw_matches - total_unique_uses} duplicate lines**")


if __name__ == '__main__':
    main()
