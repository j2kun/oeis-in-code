#!/usr/bin/env python3
"""
Search Sourcegraph for source code matching a regex pattern and output a CSV.
Processes repositories from a file and supports resume capability.

Usage:
    python sourcegraph_search.py --regex 'oeis.org/A[0-9]+' --search_query 'oeis.org/A' --repos repos.txt

Examples:
    python sourcegraph_search.py --regex 'oeis.org/A[0-9]+' --search_query 'oeis.org/A' --repos repos.txt
    python sourcegraph_search.py --regex 'oeis.org/A[0-9]+' --search_query 'oeis.org/A' --repos repos.txt --output results.csv
"""

import argparse
import csv
import json
import os
import re
import signal
import sys
import time
import urllib.parse
import urllib.request


# Global variables for graceful shutdown
should_exit = False
results_data = []
output_file = None


def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully by marking for shutdown."""
    global should_exit
    print(
        "\n\n[INFO] Interrupt received. Will save and exit after current operation...",
        file=sys.stderr,
    )
    should_exit = True


def search_sourcegraph(query: str, pattern: re.Pattern) -> list[dict]:
    """
    Search Sourcegraph using streaming API and extract matches.
    Returns list of match dictionaries.
    """
    params = urllib.parse.urlencode(
        {
            "q": query,
            "v": "V3",
        }
    )
    url = f"https://sourcegraph.com/.api/search/stream?{params}"

    req = urllib.request.Request(url)
    req.add_header("Accept", "text/event-stream")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )

    matches = []

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            event_type = None
            data_lines = []

            for line in resp:
                if should_exit:
                    break

                line = line.decode("utf-8").rstrip("\n")

                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    data_lines.append(line[6:])
                elif line == "":
                    # End of event
                    if event_type and data_lines:
                        data = "\n".join(data_lines)
                        try:
                            event_data = json.loads(data)

                            if event_type == "matches":
                                for match in event_data:
                                    match_type = match.get("type")

                                    if match_type == "content":
                                        # Extract matches from content match
                                        repo = match.get("repository")
                                        path = match.get("path")

                                        # Get line matches
                                        line_matches = match.get("lineMatches", [])
                                        for line_match in line_matches:
                                            line_number = line_match.get(
                                                "lineNumber", 0
                                            )
                                            line_text = line_match.get("line", "")

                                            # Apply regex to extract actual matches
                                            for regex_match in pattern.finditer(
                                                line_text
                                            ):
                                                matches.append(
                                                    {
                                                        "matched_string": regex_match.group(
                                                            0
                                                        ),
                                                        "repository": repo,
                                                        "file_path": path,
                                                        "line_number": line_number,
                                                        "line_content": line_text.strip(),
                                                    }
                                                )

                                    elif match_type == "path":
                                        # Path matches - apply regex to the path
                                        repo = match.get("repository")
                                        path = match.get("path")

                                        for regex_match in pattern.finditer(path):
                                            matches.append(
                                                {
                                                    "matched_string": regex_match.group(
                                                        0
                                                    ),
                                                    "repository": repo,
                                                    "file_path": path,
                                                    "line_number": 0,  # No specific line for path matches
                                                    "line_content": "",  # No line content for path matches
                                                }
                                            )

                            elif event_type == "progress":
                                stats = event_data
                                match_count = stats.get("matchCount", 0)
                                if match_count > 0:
                                    print(
                                        f"    Progress: {match_count} matches found so far...",
                                        file=sys.stderr,
                                    )

                            elif event_type == "done":
                                print(f"    Search complete", file=sys.stderr)

                        except json.JSONDecodeError:
                            pass

                    event_type = None
                    data_lines = []

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[ERROR] Sourcegraph API {e.code}: {body}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"[ERROR] Sourcegraph request failed: {e}", file=sys.stderr)
        raise

    return matches


def read_repos_file(filename: str) -> list[str]:
    """Read list of repositories from a file."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            repos = [line.strip() for line in f if line.strip()]
        print(f"[INFO] Loaded {len(repos)} repos from {filename}", file=sys.stderr)
        return repos
    except FileNotFoundError:
        print(f"[ERROR] Repos file not found: {filename}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Error reading repos file: {e}", file=sys.stderr)
        sys.exit(1)


def read_existing_results(filename: str) -> tuple[list[dict], set[str]]:
    """
    Read existing CSV results.
    Returns (list of row dicts, set of processed repos).
    """
    if not os.path.exists(filename):
        return [], set()

    rows = []
    processed_repos = set()

    try:
        with open(filename, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Handle old CSV format without line_content field
                if "line_content" not in row:
                    row["line_content"] = ""
                rows.append(row)
                processed_repos.add(row["repository"])

        print(
            f"[INFO] Loaded {len(rows)} existing results from {filename}",
            file=sys.stderr,
        )
        print(
            f"[INFO] Found {len(processed_repos)} already processed repos",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"[WARN] Error reading existing results: {e}", file=sys.stderr)
        return [], set()

    return rows, processed_repos


def write_results(filename: str, rows: list[dict]):
    """Write results to CSV file."""
    if not rows:
        print("[INFO] No results to write.", file=sys.stderr)
        return

    fieldnames = [
        "matched_string",
        "repository",
        "file_path",
        "line_number",
        "line_content",
    ]
    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[INFO] Wrote {len(rows)} rows to {filename}", file=sys.stderr)
    except Exception as e:
        print(f"[ERROR] Failed to write results: {e}", file=sys.stderr)


def process_repo(repo: str, search_query: str, pattern: re.Pattern) -> list[dict]:
    """
    Process a single repository using Sourcegraph and return list of match rows.
    """
    # Add repo: qualifier to search query
    repo_query = f"{search_query} repo:^{repo}$ count:all"

    print(f"  Query: {repo_query}", file=sys.stderr)

    try:
        matches = search_sourcegraph(repo_query, pattern)
        print(f"  Found {len(matches)} matches in {repo}", file=sys.stderr)
        return matches
    except Exception as e:
        print(f"  Error searching {repo}: {e}", file=sys.stderr)
        return []


def main():
    global should_exit, results_data, output_file

    # Set up signal handler for Ctrl-C
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(
        description="Search Sourcegraph for a regex and output CSV. Processes repos from a file with resume capability."
    )
    parser.add_argument(
        "--regex",
        required=True,
        help="Regular expression to search for (e.g. oeis.org/A[0-9]+)",
    )
    parser.add_argument(
        "--search_query",
        required=True,
        help="Search query string (e.g. oeis.org/A)",
    )
    parser.add_argument(
        "--repos",
        required=True,
        help="File containing list of repositories to process (one per line)",
    )
    parser.add_argument(
        "--output", default="results.csv", help="Output CSV file (default: results.csv)"
    )
    parser.add_argument(
        "--checkpoint_interval",
        type=int,
        default=10,
        help="Save results after processing this many repos (default: 10)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between repo queries (default: 1.0)",
    )
    args = parser.parse_args()

    output_file = args.output

    try:
        pattern = re.compile(args.regex)
    except re.error as e:
        print(f"[ERROR] Invalid regex: {e}", file=sys.stderr)
        sys.exit(1)

    # Read repos to process
    repos_to_process = read_repos_file(args.repos)

    # Read existing results
    results_data, processed_repos = read_existing_results(args.output)

    # Filter to unprocessed repos
    unprocessed_repos = [r for r in repos_to_process if r not in processed_repos]

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"[INFO] Total repos to process: {len(repos_to_process)}", file=sys.stderr)
    print(f"[INFO] Already processed: {len(processed_repos)}", file=sys.stderr)
    print(f"[INFO] Remaining to process: {len(unprocessed_repos)}", file=sys.stderr)
    print(f"[INFO] Search query: {args.search_query!r}", file=sys.stderr)
    print(f"[INFO] Regex pattern: {args.regex!r}", file=sys.stderr)
    print(f"{'='*70}\n", file=sys.stderr)

    if not unprocessed_repos:
        print("[INFO] All repos have been processed!", file=sys.stderr)
        return

    try:
        for i, repo in enumerate(unprocessed_repos, 1):
            if should_exit:
                print(f"\n[INFO] Stopping at user request.", file=sys.stderr)
                break

            print(
                f"\n[{i}/{len(unprocessed_repos)}] Processing: {repo}", file=sys.stderr
            )

            try:
                repo_results = process_repo(repo, args.search_query, pattern)
                results_data.extend(repo_results)

                # Periodically save results
                if i % args.checkpoint_interval == 0:
                    print(
                        f"\n[CHECKPOINT] Saving results after {i} repos...",
                        file=sys.stderr,
                    )
                    write_results(args.output, results_data)

            except Exception as e:
                print(f"[ERROR] Error processing {repo}: {e}", file=sys.stderr)
                print(f"[INFO] Continuing to next repo...", file=sys.stderr)
                import traceback

                traceback.print_exc(file=sys.stderr)
                continue

            # Rate limiting
            if i < len(unprocessed_repos) and not should_exit:
                time.sleep(args.delay)

            if should_exit:
                break

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)

    finally:
        # Always save results before exiting
        print(f"\n[INFO] Saving final results...", file=sys.stderr)
        write_results(args.output, results_data)

        if should_exit:
            print("[INFO] Exiting due to interrupt.", file=sys.stderr)
            sys.exit(130)  # Standard exit code for SIGINT

        print(
            f"\n[SUCCESS] Processing complete! Total results: {len(results_data)}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
