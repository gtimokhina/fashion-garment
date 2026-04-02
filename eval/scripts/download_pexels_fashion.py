#!/usr/bin/env python3
"""
Download fashion stock photos using the official Pexels API.

The website https://www.pexels.com/search/fashion/ is not meant for bulk scraping;
use the free API instead: https://www.pexels.com/api/

  # PEXELS_API_KEY is read from the repo root .env, then optional app/backend/.env, else the environment.
  python3 eval/scripts/download_pexels_fashion.py

Optional: --count 50 --query fashion --out eval/data/pexels_fashion
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Repo root = parent of eval/
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "eval" / "data" / "pexels_fashion"
API_SEARCH = "https://api.pexels.com/v1/search"
ROOT_ENV = REPO_ROOT / ".env"
BACKEND_ENV = REPO_ROOT / "app" / "backend" / ".env"

# Pexels sits behind Cloudflare. The default urllib User-Agent (Python-urllib/…) is often
# blocked with HTTP 403 and body "error code: 1010". Use a normal browser-like UA.
_CLIENT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _load_dotenv_file(path: Path) -> None:
    """Load KEY=value pairs from a .env file into os.environ if not already set."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    if text.startswith("\ufeff"):
        text = text[1:]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key:
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key not in os.environ:
            os.environ[key] = val


def load_repo_dotenv() -> None:
    """Load repo root `.env`, then optional `app/backend/.env` (same precedence as the backend)."""
    _load_dotenv_file(ROOT_ENV)
    _load_dotenv_file(BACKEND_ENV)


def fetch_page(query: str, per_page: int, page: int, api_key: str) -> dict:
    q = urllib.parse.urlencode({"query": query, "per_page": str(per_page), "page": str(page)})
    url = f"{API_SEARCH}?{q}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "Accept": "application/json",
            "User-Agent": _CLIENT_UA,
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def pick_image_url(photo: dict) -> str | None:
    src = photo.get("src") or {}
    return (
        src.get("large2x")
        or src.get("large")
        or src.get("medium")
        or src.get("original")
    )


def download_file(url: str, dest: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _CLIENT_UA},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Download images via Pexels API")
    parser.add_argument("--query", default="fashion", help="Search query (default: fashion)")
    parser.add_argument("--count", type=int, default=50, help="Target number of images (default: 50)")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output directory (default: {DEFAULT_OUT})",
    )
    args = parser.parse_args()

    load_repo_dotenv()
    api_key = (os.environ.get("PEXELS_API_KEY") or "").strip()
    if not api_key:
        print(
            "Missing PEXELS_API_KEY. Add it to the repo root `.env` or export it. "
            "Create a free key at https://www.pexels.com/api/",
            file=sys.stderr,
        )
        return 1

    target = max(1, min(args.count, 500))
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    def pexels_count() -> int:
        return len(list(out_dir.glob("pexels_*")))

    if pexels_count() >= target:
        print(f"Already have at least {target} image(s) in {out_dir}")
        return 0

    page = 1
    downloaded_this_run = 0

    while pexels_count() < target:
        need = target - pexels_count()
        per_page = min(80, max(need + 5, 15))
        try:
            data = fetch_page(args.query, per_page, page, api_key)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace") if e.fp else ""
            print(f"Pexels API HTTP {e.code}: {body[:500]}", file=sys.stderr)
            if e.code == 403 and "1010" in body:
                print(
                    "Hint: Cloudflare often blocks the default Python user-agent; this script "
                    "sets a browser User-Agent. If this persists, try another network/VPN or "
                    "confirm your API key at https://www.pexels.com/api/",
                    file=sys.stderr,
                )
            return 1
        except urllib.error.URLError as e:
            print(f"Network error: {e}", file=sys.stderr)
            return 1

        photos = data.get("photos") or []
        if not photos:
            print("No more results from API.", file=sys.stderr)
            break

        before = pexels_count()
        for photo in photos:
            if pexels_count() >= target:
                break
            pid = photo.get("id")
            url = pick_image_url(photo)
            if not url or pid is None:
                continue
            ext = Path(urllib.parse.urlparse(url).path).suffix or ".jpg"
            dest = out_dir / f"pexels_{pid}{ext}"
            if dest.exists():
                continue
            try:
                n = pexels_count() + 1
                print(f"Downloading {n}/{target}: {dest.name}")
                download_file(url, dest)
                downloaded_this_run += 1
            except (urllib.error.URLError, OSError) as e:
                print(f"Skip photo {pid}: {e}", file=sys.stderr)

        if pexels_count() >= target:
            break
        if len(photos) < per_page:
            break
        if pexels_count() == before:
            # No progress (e.g. all duplicates on this page); advance anyway
            pass
        page += 1
        time.sleep(0.35)

    final_n = pexels_count()
    print(f"Done. {final_n} image(s) in {out_dir} (new this run: {downloaded_this_run})")
    return 0 if final_n >= target else 2


if __name__ == "__main__":
    raise SystemExit(main())
