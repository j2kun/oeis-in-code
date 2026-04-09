#!/usr/bin/env python3
"""
Query Sourcegraph to get a list of repositories matching a search query.

Usage:
    python get_repos_sourcegraph.py --query "oeis.org/A"
    python get_repos_sourcegraph.py --query "oeis.org/A" --output repos.txt
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request


def search_sourcegraph_repos(query: str, max_results: int = None):
    """
    Search Sourcegraph for code matching the query and extract unique repository names.
    Uses the streaming search API.
    """
    # Search for code matches - we'll extract unique repos from the results
    search_query = f"{query} count:all"

    params = urllib.parse.urlencode({
        "q": search_query,
        "v": "V3",  # API version
    })
    url = f"https://sourcegraph.com/.api/search/stream?{params}"

    print(f"Querying Sourcegraph: {search_query!r}", file=sys.stderr)
    print(f"URL: {url}", file=sys.stderr)

    req = urllib.request.Request(url)
    req.add_header("Accept", "text/event-stream")
    req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    repos = set()

    try:
        with urllib.request.urlopen(req) as resp:
            # Parse the event stream
            event_type = None
            data_lines = []

            for line in resp:
                line = line.decode('utf-8').rstrip('\n')

                if line.startswith('event: '):
                    event_type = line[7:]  # Extract event type
                elif line.startswith('data: '):
                    data_lines.append(line[6:])  # Extract data
                elif line == '':
                    # Empty line signals end of event
                    if event_type and data_lines:
                        data = '\n'.join(data_lines)
                        try:
                            event_data = json.loads(data)

                            # Handle 'matches' event - extract repository names from any match type
                            if event_type == 'matches':
                                for match in event_data:
                                    # All match types (content, path, repo, etc.) should have a repository field
                                    repo_name = match.get('repository')
                                    if repo_name:
                                        if repo_name not in repos:
                                            repos.add(repo_name)
                                            print(f"  Found: {repo_name}", file=sys.stderr)

                                        if max_results and len(repos) >= max_results:
                                            return list(repos)

                            # Handle 'progress' event for stats
                            elif event_type == 'progress':
                                stats = event_data
                                matched_repos = stats.get('matchCount', 0)
                                if matched_repos > 0:
                                    print(f"  Progress: {len(repos)} unique repos found", file=sys.stderr)

                            # Handle 'done' event
                            elif event_type == 'done':
                                print(f"  Search complete", file=sys.stderr)

                        except json.JSONDecodeError:
                            pass  # Skip malformed JSON

                    # Reset for next event
                    event_type = None
                    data_lines = []

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[ERROR] Sourcegraph API {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    return list(repos)


def main():
    parser = argparse.ArgumentParser(
        description="Query Sourcegraph for repositories matching a search query."
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Search query (e.g., 'oeis.org/A')"
    )
    parser.add_argument(
        "--output",
        default="repos.txt",
        help="Output file for repository list (default: repos.txt)"
    )
    parser.add_argument(
        "--max_results",
        type=int,
        default=None,
        help="Maximum number of repositories to retrieve (default: unlimited)"
    )

    args = parser.parse_args()

    repos = search_sourcegraph_repos(args.query, args.max_results)

    if not repos:
        print("No repositories found.", file=sys.stderr)
        sys.exit(0)

    # Sort repositories for consistent output
    repos.sort()

    # Write to file
    with open(args.output, 'w', encoding='utf-8') as f:
        for repo in repos:
            f.write(f"{repo}\n")

    print(f"\nWrote {len(repos)} repositories to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
