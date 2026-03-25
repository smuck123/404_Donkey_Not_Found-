#!/usr/bin/env python3
import argparse
import sys
import requests

URL = "https://warsawbeerfestival.com/beer-list/"


def fetch_html() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    return r.text


def main():
    parser = argparse.ArgumentParser(description="Fetch Warsaw Beer Festival beer list HTML")
    parser.add_argument("--out", help="Save HTML to file")
    args = parser.parse_args()

    html = fetch_html()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved HTML to {args.out}")
    else:
        sys.stdout.write(html)


if __name__ == "__main__":
    main()
