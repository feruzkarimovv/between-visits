#!/usr/bin/env python3
"""Export docs/pitch/deck.html to docs/pitch/deck.pdf with headless Chromium (Playwright), one slide per page (WS4 D14).

Render the Site Signal numbers first (validation/render_numbers.py --in-place ...); this script refuses a deck that still
has an `ss` token. It prints the page count and exits 1 unless it equals the number of slides in the HTML.

    uv run --no-project --with playwright==1.63.0 python docs/pitch/export_pdf.py
    # first run on a machine: uv run --no-project --with playwright==1.63.0 playwright install chromium

Options: --html PATH (default docs/pitch/deck.html), --out PATH (default docs/pitch/deck.pdf).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE_RE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")


def count_pages(pdf: bytes) -> int:
    return len(PAGE_RE.findall(pdf))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--html", type=Path, default=ROOT / "docs" / "pitch" / "deck.html")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "pitch" / "deck.pdf")
    args = ap.parse_args(argv)

    html = args.html.resolve()
    text = html.read_text(encoding="utf-8")
    if re.search(r"\{\{\s*ss:", text):
        print(f"export: {html.name} still has ss tokens; run validation/render_numbers.py --in-place first",
              file=sys.stderr)
        return 1
    slides = len(re.findall(r'<section class="slide"', text))

    from playwright.sync_api import sync_playwright  # imported here so --help works without Playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(html.as_uri(), wait_until="load")
        page.emulate_media(media="print")
        pdf = page.pdf(print_background=True, prefer_css_page_size=True)
        browser.close()

    args.out.write_bytes(pdf)
    pages = count_pages(pdf)
    print(f"export: {args.out} ({len(pdf)} bytes): {pages} pages, {slides} slides in {html.name}")
    if pages != slides:
        print("export: FAIL, page count differs from the slide count", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
