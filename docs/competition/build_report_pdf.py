#!/usr/bin/env python3
"""Render TECHNICAL_REPORT.md to TECHNICAL_REPORT.pdf (Markdown → HTML → Chromium PDF).

    python docs/competition/build_report_pdf.py
"""

from __future__ import annotations

from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: 'DejaVu Sans', Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #0f172a; }
h1 { font-size: 20pt; margin: 0 0 6pt; } h2 { font-size: 14pt; margin: 16pt 0 6pt; border-bottom: 1px solid #cbd5e1; }
h3 { font-size: 12pt; } code { font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt; background: #f1f5f9; padding: 0 2px; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 6pt 0; page-break-inside: avoid; }
th, td { border: 1px solid #cbd5e1; padding: 3pt 5pt; vertical-align: top; } th { background: #f1f5f9; }
img { max-width: 100%; } blockquote { border-left: 3px solid #f59e0b; margin: 8pt 0; padding: 2pt 10pt; background: #fffbeb; }
"""


def nest_lists(md: str) -> str:
    """Python-Markdown nests lists at 4 spaces; the report uses 2 (CommonMark style)."""
    out = []
    for line in md.splitlines():
        stripped = line.lstrip(" ")
        n = len(line) - len(stripped)
        out.append(" " * (n * 2) + stripped if n and n % 2 == 0 else line)
    return "\n".join(out)


def main() -> None:
    md = nest_lists((HERE / "TECHNICAL_REPORT.md").read_text())
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    tmp = HERE / "_report.html"
    tmp.write_text(html)
    chrome = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chrome if Path(chrome).exists() else None)
        page = b.new_page()
        page.goto(tmp.resolve().as_uri(), wait_until="networkidle")
        page.pdf(path=str(HERE / "TECHNICAL_REPORT.pdf"), format="A4", print_background=True)
        b.close()
    tmp.unlink()
    print(HERE / "TECHNICAL_REPORT.pdf")


if __name__ == "__main__":
    main()
