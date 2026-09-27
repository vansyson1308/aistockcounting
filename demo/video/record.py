#!/usr/bin/env python3
"""Record the three demo scenarios in a phone viewport with Playwright.

    python demo/video/record.py --base-url https://dxxxx.cloudfront.net
    python demo/video/record.py --base-url http://localhost --demo-dir <dir>   # rehearsal

Writes ``demo/video/clips/tray_{a,b,c}.webm`` (iPhone 13 viewport, 390x844) and ``clips/record_log.json``, which lists each scenario's agent
decision so that the narration can be checked against what actually happened.

Scenarios (SPEC §9):
  A: a clean photo that matches POS, so the agent auto-accepts.
  B: a glare photo, so the agent requests a specific re-shot. The re-shot is accepted.
  C: a dense tray with a POS mismatch. The agent tiles and zooms, compares with
     yesterday's approved photo, and escalates; a manager then approves it on
     the review page. Yesterday's photo is uploaded first, off camera, through
     the API, and approved if needed.

Tray codes get a per-run suffix, so earlier rehearsals never become
"yesterday's approved photo".
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import httpx
import yaml
from playwright.sync_api import Page, expect, sync_playwright

HERE = Path(__file__).resolve().parent
CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
]
TIMEOUT_MS = 90_000


def slow_scroll(page: Page, total: int = 2400, step: int = 120, pause_ms: int = 140) -> None:
    for _ in range(max(1, total // step)):
        page.mouse.wheel(0, step)
        page.wait_for_timeout(pause_ms)


def fill_form(page: Page, tray_code: str, staff: str, pos: int | None) -> None:
    page.get_by_label("Tray code").fill("")
    page.get_by_label("Tray code").type(tray_code, delay=60)
    page.get_by_label("Staff ID").fill("")
    page.get_by_label("Staff ID").type(staff, delay=60)
    if pos is not None:
        page.get_by_label("POS count").fill("")
        page.get_by_label("POS count").type(str(pos), delay=90)


def upload_and_count(page: Page, image: Path, button: str = "Count this tray") -> None:
    page.locator("input[type=file]").set_input_files(str(image))
    page.wait_for_timeout(900)
    page.get_by_role("button", name=button).click()


def wait_outcome(page: Page) -> str:
    outcomes = {
        "auto_accept": page.get_by_text("Auto-accepted", exact=True),
        "request_recapture": page.get_by_role("button", name="Retake photo"),
        "escalate": page.get_by_role("link", name="Open review"),
    }
    deadline = time.time() + TIMEOUT_MS / 1000
    while time.time() < deadline:
        for name, loc in outcomes.items():
            if loc.count() and loc.first.is_visible():
                return name
        page.wait_for_timeout(250)
    raise TimeoutError("no agent outcome appeared")


def seed_previous(base: str, tenant: str | None, tray: str, image: Path, true_count: int) -> str:
    """Upload yesterday's photo for tray C through the API and make sure it is approved."""
    headers = {"X-TENANT-KEY": tenant} if tenant else {}
    api = f"{base}/api/v1"
    with httpx.Client(timeout=120, headers=headers) as c:
        r = c.post(
            f"{api}/scans",
            files={"image": (image.name, image.read_bytes(), "image/jpeg")},
            data={"branch_code": "MAIN", "tray_code": tray, "staff_id": "demo-seed", "expected_count": str(true_count)},
        )
        r.raise_for_status()
        scan = r.json()["data"]["scan"]
        if scan["status"] == "awaiting_approval":
            c.post(
                f"{api}/scans/{scan['id']}/approve",
                json={"approver_id": "demo-seed", "decision": "correct", "corrected_count": true_count,
                      "note": "yesterday's approved photo for the demo"},
            ).raise_for_status()
        elif scan["status"] not in {"reviewed"}:
            raise RuntimeError(f"previous photo ended in status {scan['status']}; retake C_prev")
        return scan["id"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "demo.yaml"))
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--demo-dir", default=None)
    ap.add_argument("--out", default=str(HERE / "clips"))
    ap.add_argument("--only", default="abc")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    base = (args.base_url or cfg["base_url"]).rstrip("/")
    demo_dir = Path(args.demo_dir or (HERE / cfg["images_dir"])).resolve()
    trays = cfg["trays"]
    suffix = time.strftime("%m%d%H%M")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log: dict[str, dict] = {}
    exe = next((p for p in CHROMIUM_CANDIDATES if Path(p).exists()), None)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, slow_mo=120)
        device = dict(p.devices["iPhone 13"])

        def scenario(key: str, body) -> None:
            vid_dir = out / f"_raw_{key}"
            shutil.rmtree(vid_dir, ignore_errors=True)
            # Playwright scales recordings down, never up, so record at the CSS
            # viewport size. build.sh scales it to 1000 px tall (about 1.2x).
            vp = device["viewport"]
            ctx = browser.new_context(**device, record_video_dir=str(vid_dir),
                                      record_video_size={"width": vp["width"], "height": vp["height"]})
            page = ctx.new_page()
            page.set_default_timeout(TIMEOUT_MS)
            try:
                log[key] = body(page)
            finally:
                video = page.video
                ctx.close()
                if video:
                    shutil.move(video.path(), out / f"tray_{key}.webm")
                shutil.rmtree(vid_dir, ignore_errors=True)
            print(key, log.get(key))

        def tray_a(page: Page) -> dict:
            t = trays["A"]
            page.goto(f"{base}/scan", wait_until="networkidle")
            page.wait_for_timeout(1200)
            fill_form(page, f"{t['tray_code']}-{suffix}", "EMP-07", t["pos"])
            upload_and_count(page, demo_dir / t["image"])
            outcome = wait_outcome(page)
            page.wait_for_timeout(1500)
            slow_scroll(page, 2600)
            page.wait_for_timeout(1500)
            return {"decision": outcome}

        def tray_b(page: Page) -> dict:
            t = trays["B"]
            page.goto(f"{base}/scan", wait_until="networkidle")
            page.wait_for_timeout(1000)
            fill_form(page, f"{t['tray_code']}-{suffix}", "EMP-07", t["pos"])
            upload_and_count(page, demo_dir / t["image"])
            first = wait_outcome(page)
            page.wait_for_timeout(3500)  # let the viewer read the instruction
            second = None
            if first == "request_recapture":
                page.get_by_role("button", name="Retake photo").click()
                page.wait_for_timeout(1200)
                upload_and_count(page, demo_dir / t["reshot"], button="Count retaken photo")
                second = wait_outcome(page)
                page.wait_for_timeout(1500)
                slow_scroll(page, 1800)
                page.wait_for_timeout(1200)
            return {"decision": first, "reshot_decision": second}

        def tray_c(page: Page) -> dict:
            t = trays["C"]
            code = f"{t['tray_code']}-{suffix}"
            seed_previous(base, cfg.get("tenant"), code, demo_dir / t["previous"], t["previous_count"])
            page.goto(f"{base}/scan", wait_until="networkidle")
            page.wait_for_timeout(1000)
            fill_form(page, code, "EMP-07", t["pos"])
            upload_and_count(page, demo_dir / t["image"])
            outcome = wait_outcome(page)
            page.wait_for_timeout(2500)
            slow_scroll(page, 2400)
            approved = False
            tools: list[str] = []
            if outcome == "escalate":
                page.get_by_role("link", name="Open review").first.click()
                page.wait_for_load_state("networkidle")
                scan_id = page.url.rstrip("/").split("/")[-1]
                headers = {"X-TENANT-KEY": cfg["tenant"]} if cfg.get("tenant") else {}
                trace = httpx.get(f"{base}/api/v1/scans/{scan_id}/trace", headers=headers, timeout=30).json()
                tools = [s["tool"] for s in trace["data"]["steps"]]
                narrated = {"tile_detect", "zoom_recount", "compare_previous"}
                missing = sorted(narrated - set(tools))
                if missing:
                    print(f"WARNING: tray C narration mentions {missing}, but this run did not use them. "
                          "Edit segments.yaml (tray_c) to match the real trace.")
                page.wait_for_timeout(2000)
                slow_scroll(page, 5200, step=140, pause_ms=160)
                page.get_by_label("Approver ID").fill("MGR-01")
                note = page.get_by_label("Note (optional)")
                if note.count():
                    note.type("Confirmed: one ring sold, POS not yet updated.", delay=35)
                page.get_by_role("button", name="Approve agent count").click()
                expect(page.get_by_text("Final decision")).to_be_visible()
                page.wait_for_timeout(2500)
                approved = True
            return {"decision": outcome, "approved": approved, "tools": tools}

        for key, fn in (("a", tray_a), ("b", tray_b), ("c", tray_c)):
            if key in args.only:
                scenario(key, fn)
        browser.close()
    (out / "record_log.json").write_text(json.dumps(log, indent=2) + "\n")


if __name__ == "__main__":
    main()
