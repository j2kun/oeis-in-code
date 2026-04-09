#!/usr/bin/env python3
"""
Analyze results.csv and print statistics about OEIS matches.
"""

import csv
import os
from collections import Counter

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


def print_match_details(details, max_display=10):
    """Print details of matches with limit."""
    total = len(details)
    displayed = min(total, max_display)

    for i, detail in enumerate(details[:max_display], 1):
        print(f"   [{i}] Repository: {detail['repository']}")
        print(f"       File: {detail['file_path']}")
        print(f"       Line: {detail['line_number']}")
        content = detail['line_content']
        if len(content) > 100:
            content = content[:97] + "..."
        print(f"       Content: {content}")
        print()

    if total > displayed:
        print(f"   ... and {total - displayed} more occurrences")
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
        print(f"   [{i}] {matched_string} (A{oeis_num:06d})")
        print(f"       Repository: {detail['repository']}")
        print(f"       File: {detail['file_path']}")
        print(f"       Line: {detail['line_number']}")
        content = detail['line_content']
        if len(content) > 100:
            content = content[:97] + "..."
        print(f"       Content: {content}")
        print()


def main():
    # Read skip files
    repos_to_skip = set()
    with open('repos_to_skip.txt', 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                repos_to_skip.add(line)

    files_to_skip = set()
    with open('files_to_skip.txt', 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                files_to_skip.add(line)

    # Read CSV and collect data
    all_matches = []
    all_matches_details = {}  # matched_string -> list of details
    filtered_matches = []
    filtered_matches_details = {}  # matched_string -> list of details
    all_oeis_with_numbers = []  # List of (oeis_num, matched_string, detail)
    filtered_oeis_with_numbers = []  # List of (oeis_num, matched_string, detail)

    with open('results.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            matched_string = row['matched_string']
            repository = row['repository']
            file_path = row['file_path']

            detail = {
                'repository': repository,
                'file_path': file_path,
                'line_number': row.get('line_number', ''),
                'line_content': row.get('line_content', '')
            }

            # Collect for statistic 1
            all_matches.append(matched_string)
            if matched_string not in all_matches_details:
                all_matches_details[matched_string] = []
            all_matches_details[matched_string].append(detail)

            # Collect for statistic 2 (highest A numbers)
            oeis_num = extract_oeis_number(matched_string)
            if oeis_num is not None:
                all_oeis_with_numbers.append((oeis_num, matched_string, detail))

            # Check for statistic 3 & 4 (filtered)
            # Skip if repository is in repos_to_skip
            if repository in repos_to_skip:
                continue

            # Skip if trailing filename is in files_to_skip
            filename = os.path.basename(file_path)
            if filename in files_to_skip:
                continue

            filtered_matches.append(matched_string)
            if matched_string not in filtered_matches_details:
                filtered_matches_details[matched_string] = []
            filtered_matches_details[matched_string].append(detail)

            # Collect for highest OEIS numbers among filtered matches
            if oeis_num is not None:
                filtered_oeis_with_numbers.append((oeis_num, matched_string, detail))

    # Compute statistics
    print("=" * 70)
    print("OEIS Results Statistics")
    print("=" * 70)
    print()

    # Statistic 1: Most common matched_string
    if all_matches:
        counter = Counter(all_matches)
        most_common = counter.most_common(1)[0]
        print(f"1. Most common matched_string among all matches:")
        print(f"   {most_common[0]} (appears {most_common[1]} times)")
        print()
        print_match_details(all_matches_details[most_common[0]])

    # Statistic 2: Top 20 highest OEIS numbers from distinct repos
    if all_oeis_with_numbers:
        top_20 = get_top_n_from_distinct_repos(all_oeis_with_numbers, 20)
        print(f"2. Top 20 highest matched_strings (by A number, distinct repos):")
        print()
        print_highest_matches(top_20)

    # Statistic 3: Most common filtered matched_string
    if filtered_matches:
        counter = Counter(filtered_matches)
        most_common = counter.most_common(1)[0]
        print(f"3. Most common matched_string (filtered):")
        print(f"   Excludes repos in repos_to_skip.txt and files in files_to_skip.txt")
        print(f"   {most_common[0]} (appears {most_common[1]} times)")
        print()
        print_match_details(filtered_matches_details[most_common[0]])

    # Statistic 4: Top 20 highest OEIS numbers (filtered) from distinct repos
    if filtered_oeis_with_numbers:
        top_20_filtered = get_top_n_from_distinct_repos(filtered_oeis_with_numbers, 20)
        print(f"4. Top 20 highest matched_strings (filtered, by A number, distinct repos):")
        print(f"   Excludes repos in repos_to_skip.txt and files in files_to_skip.txt")
        print()
        print_highest_matches(top_20_filtered)

    # Additional summary
    print("=" * 70)
    print(f"Total matches: {len(all_matches)}")
    print(f"Total matches after filtering: {len(filtered_matches)}")
    print(f"Unique matched_strings: {len(set(all_matches))}")
    print(f"Unique matched_strings (filtered): {len(set(filtered_matches))}")
    print("=" * 70)


if __name__ == '__main__':
    main()
