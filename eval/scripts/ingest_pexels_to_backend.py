#!/usr/bin/env python3
"""
POST Pexels downloads (eval/data/pexels_fashion) to the running backend, same as UI upload:
save → classify → DB row. Then PATCH annotations with tags + notes.

Requires the API up (e.g. uvicorn) and OPENAI_* set for classification.

  python eval/scripts/ingest_pexels_to_backend.py
  python eval/scripts/ingest_pexels_to_backend.py --base-url http://127.0.0.1:8000 --dry-run
"""

from __future__ import annotations

import argparse
import errno
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Repo root = parent of eval/
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "eval" / "data" / "pexels_fashion"

_CLIENT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_DEFAULT_TAGS = ["pexels", "eval", "stock"]
_DEFAULT_NOTES = "Imported from Pexels (bulk download + ingest script)."

_BACKEND_HINT = """\
Connection refused — no HTTP server at {url}.

Start the API first (from app/backend with your venv activated), then retry:

  cd app/backend && uvicorn main:app --reload --host 127.0.0.1 --port 8000

If the API runs elsewhere, set --base-url or BACKEND_URL (e.g. http://127.0.0.1:8000).
"""


def _is_connection_refused(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.URLError) and exc.reason is not None:
        r = exc.reason
        if isinstance(r, OSError):
            return r.errno == errno.ECONNREFUSED
    return False


def ping_health(base_url: str, timeout: int = 5) -> None:
    """GET /health — fails fast if the backend is not running."""
    url = f"{base_url.rstrip('/')}/health"
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": _CLIENT_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def _multipart_body(
    parts: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    """Build multipart/form-data body. Each part: field name, filename, raw bytes, content-type."""
    boundary = f"----PythonIngest{os.urandom(8).hex()}"
    crlf = b"\r\n"
    chunks: list[bytes] = []
    for field_name, filename, raw, ctype in parts:
        chunks.append(f"--{boundary}".encode() + crlf)
        disp = (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'
        )
        chunks.append(disp.encode() + crlf)
        chunks.append(f"Content-Type: {ctype}".encode() + crlf)
        chunks.append(crlf)
        chunks.append(raw)
        chunks.append(crlf)
    chunks.append(f"--{boundary}--".encode() + crlf)
    return b"".join(chunks), boundary


def _guess_mime(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    return mt or "application/octet-stream"


def post_upload(base_url: str, path: Path, timeout: int) -> dict:
    """POST one file to /api/images/upload. Returns parsed JSON."""
    url = f"{base_url.rstrip('/')}/api/images/upload"
    raw = path.read_bytes()
    body, boundary = _multipart_body([("files", path.name, raw, _guess_mime(path))])
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": _CLIENT_UA,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def patch_annotations(
    base_url: str,
    image_id: int,
    tags: list[str],
    notes: str,
    timeout: int,
) -> dict:
    url = f"{base_url.rstrip('/')}/api/images/{image_id}/annotations"
    payload = json.dumps({"tags": tags, "notes": notes}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        method="PATCH",
        headers={
            "Content-Type": "application/json",
            "User-Agent": _CLIENT_UA,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def list_pexels_files(directory: Path) -> list[Path]:
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    out: list[Path] = []
    for p in sorted(directory.iterdir()):
        if p.is_file() and p.name.startswith("pexels_") and p.suffix.lower() in exts:
            out.append(p)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload Pexels eval images to the Fashion Garment API and set annotations.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help=f"Folder with pexels_* images (default: {DEFAULT_DIR})",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BACKEND_URL", "http://127.0.0.1:8000"),
        help="API base URL (default: http://127.0.0.1:8000 or BACKEND_URL)",
    )
    parser.add_argument(
        "--tags",
        default="",
        help=f"Extra comma-separated tags (always added: {', '.join(_DEFAULT_TAGS)})",
    )
    parser.add_argument(
        "--notes",
        default=_DEFAULT_NOTES,
        help="Annotation notes for every ingested image",
    )
    parser.add_argument(
        "--upload-timeout",
        type=int,
        default=300,
        help="Seconds for each upload+classify request (default: 300)",
    )
    parser.add_argument(
        "--patch-timeout",
        type=int,
        default=60,
        help="Seconds for each annotations PATCH (default: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files only; do not call the API",
    )
    args = parser.parse_args()

    root = args.dir.resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    extra = [t.strip() for t in args.tags.split(",") if t.strip()]
    tags = list(dict.fromkeys([*_DEFAULT_TAGS, *extra]))  # stable dedupe

    files = list_pexels_files(root)
    if not files:
        print(f"No pexels_* images found under {root}")
        return 0

    if not args.dry_run:
        try:
            ping_health(args.base_url)
        except urllib.error.URLError as e:
            if _is_connection_refused(e):
                print(_BACKEND_HINT.format(url=args.base_url.rstrip("/")), file=sys.stderr)
                return 1
            print(f"Cannot reach API at {args.base_url!r}: {e}", file=sys.stderr)
            return 1
        except OSError as e:
            print(f"Cannot reach API at {args.base_url!r}: {e}", file=sys.stderr)
            return 1

    print(f"Found {len(files)} file(s) under {root}")
    if args.dry_run:
        for p in files:
            print(f"  would upload: {p.name}")
        print(f"tags: {tags}")
        print(f"notes: {args.notes!r}")
        return 0

    ok = 0
    failed = 0
    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] Upload {path.name} …", flush=True)
        try:
            data = post_upload(args.base_url, path, args.upload_timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace") if e.fp else ""
            print(f"  HTTP {e.code}: {body[:400]}", file=sys.stderr)
            failed += 1
            continue
        except urllib.error.URLError as e:
            print(f"  Network error: {e}", file=sys.stderr)
            if _is_connection_refused(e):
                print(_BACKEND_HINT.format(url=args.base_url.rstrip("/")), file=sys.stderr)
                return 1
            failed += 1
            continue

        items = data.get("items") or []
        errs = data.get("errors") or []
        if errs:
            for err in errs:
                print(
                    f"  Upload error: {err.get('filename')}: {err.get('detail')}",
                    file=sys.stderr,
                )
            failed += 1
            continue
        if not items:
            print("  No items in response", file=sys.stderr)
            failed += 1
            continue

        image_id = items[0]["id"]
        try:
            patch_annotations(
                args.base_url,
                image_id,
                tags,
                args.notes,
                args.patch_timeout,
            )
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace") if e.fp else ""
            print(
                f"  Uploaded id={image_id} but annotations failed HTTP {e.code}: {body[:300]}",
                file=sys.stderr,
            )
            failed += 1
            continue
        except urllib.error.URLError as e:
            print(f"  Annotations network error: {e}", file=sys.stderr)
            if _is_connection_refused(e):
                print(_BACKEND_HINT.format(url=args.base_url.rstrip("/")), file=sys.stderr)
                return 1
            failed += 1
            continue

        print(f"  → id={image_id}, tags={len(tags)}")
        ok += 1

    print(f"Done. ok={ok} failed={failed}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
