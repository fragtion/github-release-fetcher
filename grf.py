#!/usr/bin/env python3
"""
Git Release Fetcher v1.1b
Author: Dimitri Pappas <https://github.com/fragtion>
License: MIT

Retrieves a list of file assets for a given GitHub repo release and optionally downloads them.
If a specific release is not provided, the script defaults to the latest release.
Supports filtering with --include and --exclude, resuming interrupted downloads, and verifies 
downloaded file sizes by comparing with the release manifest as a simple sanity check.
"""

import os
import sys
import json
import time
import argparse
import urllib.request
from urllib.error import HTTPError, URLError

VERSION = "v1.1b"
PROGRAM_NAME = "Github Release Fetcher"

def format_size(size):
    """Convert file size in bytes to a human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} PB"  # Just in case someone has a petabyte-sized file

def format_speed(speed):
    """Format download speed into human-readable format."""
    if speed < 1024:
        return f"{speed:.2f} B/s"
    elif speed < 1024 * 1024:
        return f"{speed / 1024:.2f} KB/s"
    else:
        return f"{speed / (1024 * 1024):.2f} MB/s"

def download_file_with_progress(url, target_path, expected_size=None):
    """Download a file with progress bar and support for resuming."""
    try:
        # Check if the file already exists and get its size
        if os.path.exists(target_path):
            existing_size = os.path.getsize(target_path)
            if expected_size and existing_size == expected_size:
                print(f"File already exists and matches expected size: {target_path}")
                return
            headers = {"Range": f"bytes={existing_size}-"}
            req = urllib.request.Request(url, headers=headers)
            mode = "ab"  # Append to existing file
        else:
            req = urllib.request.Request(url)
            mode = "wb"  # Write new file
            existing_size = 0

        with urllib.request.urlopen(req) as response, open(target_path, mode) as target_file:
            file_size = int(response.headers.get("Content-Length", 0)) + existing_size
            chunk_size = 1024 * 1024  # 1 MB chunks
            bytes_so_far = existing_size
            start_time = time.time()

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break

                target_file.write(chunk)
                bytes_so_far += len(chunk)
                percent_complete = (bytes_so_far / file_size) * 100

                # Calculate download speed
                elapsed_time = time.time() - start_time
                download_speed = bytes_so_far / elapsed_time if elapsed_time > 0 else 0

                # Display progress bar
                bar_length = 50
                num_chars = int(percent_complete / (100 / bar_length))
                progress_bar = "[" + "#" * num_chars + "." * (bar_length - num_chars) + \
                               f"] {int(percent_complete)}% - {format_speed(download_speed)}"
                sys.stdout.write(f"\r{progress_bar}")
                sys.stdout.flush()

            sys.stdout.write("\n")  # Move to the next line after completion

        # Verify file size
        if expected_size and os.path.getsize(target_path) != expected_size:
            print(f"Error: File size mismatch for {target_path}")
        else:
            print(f"Done: {target_path}")

    except (HTTPError, URLError) as e:
        print(f"Error: Failed to download {target_path} - {e}")

def fetch_release_data(repo_url, release_tag=None):
    """Fetch release data from GitHub API."""
    # Normalize the repository URL
    if repo_url.startswith("https://api.github.com/repos/"):
        # Extract owner and repo from the API URL
        parts = repo_url[len("https://api.github.com/repos/"):].split("/")
        if len(parts) < 2:
            print("Invalid GitHub API URL.")
            sys.exit(1)
        owner, repo = parts[0], parts[1]
    elif repo_url.startswith("https://github.com/"):
        # Extract owner and repo from the GitHub URL
        parts = repo_url[len("https://github.com/"):].split("/")
        if len(parts) < 2:
            print("Invalid GitHub repository URL.")
            sys.exit(1)
        owner, repo = parts[0], parts[1]
        
        # Check if the URL is a release tag URL (e.g., https://github.com/owner/repo/releases/tag/7.17)
        if "releases/tag/" in repo_url:
            url_release_tag = repo_url.split("releases/tag/")[-1].strip("/")
            if release_tag and release_tag != url_release_tag:
                print(f"Error: Conflicting release tags. URL specifies '{url_release_tag}', but --release specifies '{release_tag}'.")
                sys.exit(1)
            release_tag = url_release_tag
    else:
        print("Unsupported URL format. Please provide a GitHub repository or API URL.")
        sys.exit(1)

    # Construct the API URL
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    if release_tag:
        api_url += f"/tags/{release_tag}"
    else:
        api_url += "/latest"

    try:
        with urllib.request.urlopen(api_url) as response:
            return json.loads(response.read().decode())
    except (HTTPError, URLError) as e:
        print(f"Error fetching release data: {e}")
        sys.exit(1)

def filter_assets(assets, include=None, exclude=None):
    """Filter assets based on include/exclude lists."""
    if include and exclude:
        print("Error: --include and --exclude are mutually exclusive.")
        sys.exit(1)

    if include:
        return [asset for asset in assets if asset["name"] in include]
    elif exclude:
        return [asset for asset in assets if asset["name"] not in exclude]
    else:
        return assets

def main():
    parser = argparse.ArgumentParser(
        description=f"{PROGRAM_NAME} {VERSION} by Dimitri Pappas <https://github.com/fragtion>",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("url", help="GitHub repository URL or API URL")
    parser.add_argument("-r", "--release", help="Specific release tag (e.g., 7.18.1)")
    parser.add_argument("-d", "--download", action="store_true", help="Download release files")
    parser.add_argument("-o", "--output", default=".", help="Output directory for downloaded files")
    parser.add_argument("-i", "--include", nargs="+", help="Only download these files")
    parser.add_argument("-e", "--exclude", nargs="+", help="Exclude these files from download")
    parser.add_argument("--version", action="version", version=f"{PROGRAM_NAME} {VERSION}")
    args = parser.parse_args()

    # Fetch release data
    release_data = fetch_release_data(args.url, args.release)
    release_tag = release_data["tag_name"]
    assets = release_data.get("assets", [])

    # Filter assets based on include/exclude
    assets = filter_assets(assets, args.include, args.exclude)

    print(f"Release: {release_tag}")
    print("Files:")
    for asset in assets:
        print(f"  {asset['name']} ({format_size(asset['size'])})")

    # Download files if requested
    if args.download:
        output_dir = os.path.join(args.output, release_tag)
        os.makedirs(output_dir, exist_ok=True)
        print(f"\nDownloading files to: {output_dir}")

        for asset in assets:
            file_url = asset["browser_download_url"]
            file_path = os.path.join(output_dir, asset["name"])
            print(f"\nDownloading: {asset['name']} ({format_size(asset['size'])})")
            download_file_with_progress(file_url, file_path, asset["size"])

if __name__ == "__main__":
    main()
