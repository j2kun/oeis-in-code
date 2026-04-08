#!/usr/bin/env python3
"""
Search GitHub for source code matching a regex pattern and output a CSV.

Usage:
    python github_search.py <regex> [options]

Examples:
    python github_search.py 'oeis.org/A'
"""

import argparse
import csv
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import json


def github_search_code(query: str, token: str, per_page: int, max_pages):
    """Yield raw code search result items from GitHub API."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    page = 1
    fetched = 0
    while page <= max_pages:
        params = urllib.parse.urlencode(
            {"q": query, "per_page": per_page, "page": page}
        )
        url = f"https://api.github.com/search/code?{params}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"[ERROR] GitHub API {e.code}: {body}", file=sys.stderr)
            if e.code == 403:
                print(
                    "[ERROR] Rate limited or forbidden. Supply a --token.",
                    file=sys.stderr,
                )
            break

        items = data.get("items", [])
        if not items:
            break

        yield from items
        fetched += len(items)

        total = data.get("total_count", 0)
        print(
            f"  Fetched {fetched}/{min(total, max_pages * per_page)} results...",
            file=sys.stderr,
        )

        if fetched >= total:
            break
        page += 1
        time.sleep(1)  # respect secondary rate limits


def fetch_file_content(repo_full_name: str, file_path: str, token: str) -> str | None:
    """Fetch raw file content from GitHub."""
    encoded_path = urllib.parse.quote(file_path, safe="/")
    url = f"https://api.github.com/repos/{repo_full_name}/contents/{encoded_path}"
    headers = {
        "Accept": "application/vnd.github.raw+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode(errors="replace")
    except Exception as e:
        print(
            f"[WARN] Could not fetch {repo_full_name}/{file_path}: {e}", file=sys.stderr
        )
        return None


def find_matches_in_content(content: str, pattern: re.Pattern) -> list[tuple[str, int]]:
    """Return list of (matched_string, line_number) for all matches."""
    results = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        for match in pattern.finditer(line):
            results.append((match.group(0), lineno))
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Search GitHub code for a regex and output CSV."
    )
    parser.add_argument(
        "--regex",
        help="Regular expression to search for (e.g. oeis.org/A[0-9]+)",
    )
    parser.add_argument(
        "--search_query",
        help="Search query to use since GH doesn't support regex in search",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub personal access token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--output", default="results.csv", help="Output CSV file (default: results.csv)"
    )
    parser.add_argument(
        "--max_results",
        type=int,
        default=1000000,
        help="Max number of GitHub search results to process (default: 100)",
    )
    args = parser.parse_args()

    if not args.token:
        print(
            "[WARN] No GitHub token provided. Unauthenticated requests are rate-limited to 10/min.",
            file=sys.stderr,
        )

    try:
        pattern = re.compile(args.regex)
    except re.error as e:
        print(f"[ERROR] Invalid regex: {e}", file=sys.stderr)
        sys.exit(1)

    search_query = args.search_query
    print(f"GitHub search query: {search_query!r}", file=sys.stderr)

    if args.max_results < 100:
        per_page = args.max_results
    else:
        per_page = 100
    max_pages = max(1, args.max_results // per_page)

    rows = []
    seen_files = set()

    for item in github_search_code(
        search_query, args.token, per_page=per_page, max_pages=max_pages
    ):
        repo = item["repository"]["full_name"]
        path = item["path"]
        key = (repo, path)
        if key in seen_files:
            continue
        seen_files.add(key)

        print(f"  Scanning {repo}/{path} ...", file=sys.stderr)
        content = fetch_file_content(repo, path, args.token)
        if content is None:
            continue

        matches = find_matches_in_content(content, pattern)
        for matched_str, lineno in matches:
            rows.append(
                {
                    "matched_string": matched_str,
                    "repository": repo,
                    "file_path": path,
                    "line_number": lineno,
                }
            )

        time.sleep(0.3)  # gentle rate limiting on contents API

    if not rows:
        print("No matches found.", file=sys.stderr)
        sys.exit(0)

    fieldnames = ["matched_string", "repository", "file_path", "line_number"]
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
