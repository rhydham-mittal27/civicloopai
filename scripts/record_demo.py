"""Record a headless screen video of the whole CivicLoop demo, with captions and a visible cursor.

    pip install playwright
    playwright install chromium
    python scripts/record_demo.py                      # records every scene it can reach
    python scripts/record_demo.py --no-mobile          # web only
    python scripts/record_demo.py --speed 1.5          # slower and calmer (1.0 = default pace)
    python scripts/record_demo.py --out my_demo        # where the videos go

What must be running first (the same setup as the screenshots):

    backend            http://127.0.0.1:8000   seeded with the demo accounts and demo data (python -m civicloop.demo)
    web app            http://localhost:3000   (npm run dev, or npm run start)
    resident app web   http://localhost:8082   (optional) web build of the resident phone app
    crew app web       http://localhost:8083   (optional) web build of the crew phone app

The phone-app addresses come from `python mobile/scripts/preview_server.py <export-dir> <port>`, see mobile/README.md.

Output: one .webm per scene in the output folder, numbered in the order they are meant to play, plus demo.mp4 with
everything joined when ffmpeg is installed. Scenes that cannot run (a page not reachable, a button not found) are
skipped with a message and the recording carries on, so a partial demo is still produced.

Accounts: the demo accounts from the seeding script. Override with environment variables, e.g.
    DEMO_SUPERVISOR=you@example.org:your-password python scripts/record_demo.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import sys
import time
import urllib.request
import zlib
from pathlib import Path

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sys.exit("Playwright is not installed. Run: pip install playwright && playwright install chromium")

WEB = os.getenv("DEMO_WEB", "http://localhost:3000")
API = os.getenv("DEMO_API", "http://127.0.0.1:8000")
RESIDENT_APP = os.getenv("DEMO_RESIDENT_APP", "http://localhost:8082")
CREW_APP = os.getenv("DEMO_CREW_APP", "http://localhost:8083")


def account(env: str, default: str) -> tuple[str, str]:
    email, _, password = os.getenv(env, default).partition(":")
    return email, password


RESIDENT = account("DEMO_RESIDENT", "resident@civic.test:resident-pass-1234")
SUPERVISOR = account("DEMO_SUPERVISOR", "supervisor@civic.test:supervisor-pass-123")
DRIVER = account("DEMO_DRIVER", "worker@civic.test:worker-pass-123456")
DRIVER_NAME = os.getenv("DEMO_DRIVER_NAME", "Karan Singh")

DESKTOP = {"width": 1280, "height": 720}
PHONE = {"width": 390, "height": 844}
PLACE = {"latitude": 30.7398, "longitude": 76.7827, "accuracy": 15}  # Sector 17, Chandigarh

# ------------------------------------------------------------------------------------------------ page furniture

OVERLAY_JS = r"""
(() => {
  if (window.__demoReady) return;
  window.__demoReady = true;
  const style = document.createElement("style");
  style.textContent = `
    #__cursor{position:fixed;z-index:2147483647;width:22px;height:22px;margin:-4px 0 0 -4px;pointer-events:none;
      transition:transform .08s ease-out;left:0;top:0}
    #__cursor svg{filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))}
    .__ripple{position:fixed;z-index:2147483646;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
      border:3px solid #e2621f;pointer-events:none;animation:__rp .6s ease-out forwards}
    @keyframes __rp{to{transform:scale(3.4);opacity:0}}
    #__caption{position:fixed;z-index:2147483647;left:50%;bottom:26px;transform:translateX(-50%);max-width:82%;
      padding:12px 22px;border-radius:14px;background:rgba(20,33,61,.92);color:#fff;font:600 19px/1.35 system-ui,Segoe UI,sans-serif;
      text-align:center;box-shadow:0 8px 28px rgba(0,0,0,.25);pointer-events:none;opacity:0;transition:opacity .25s}
    #__caption.on{opacity:1}
  `;
  const mount = () => {
    document.head.appendChild(style);
    const cur = document.createElement("div");
    cur.id = "__cursor";
    cur.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2l15 8-6.5 1.8L8.5 18z" fill="#fff" stroke="#14213d" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(cur);
    const cap = document.createElement("div");
    cap.id = "__caption";
    document.body.appendChild(cap);
    window.addEventListener("mousemove", (e) => { cur.style.transform = `translate(${e.clientX}px,${e.clientY}px)`; }, true);
    window.addEventListener("mousedown", (e) => {
      const r = document.createElement("div");
      r.className = "__ripple";
      r.style.left = e.clientX + "px";
      r.style.top = e.clientY + "px";
      document.body.appendChild(r);
      setTimeout(() => r.remove(), 700);
    }, true);
    window.__caption = (text) => {
      cap.textContent = text || "";
      cap.classList.toggle("on", !!text);
    };
  };
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);
})();
"""


class Pace:
    """Every wait goes through here so one flag slows or speeds the whole recording."""

    def __init__(self, speed: float) -> None:
        self.speed = max(0.2, speed)

    def wait(self, page, seconds: float) -> None:
        page.wait_for_timeout(int(seconds * 1000 * self.speed))


class Recorder:
    def __init__(self, browser, out: Path, pace: Pace) -> None:
        self.browser, self.out, self.pace = browser, out, pace
        self.clips: list[tuple[Path, dict]] = []
        self.report: list[tuple[str, str]] = []
        self.index = 0
        self.state: dict[str, str] = {}

    def scene(self, name: str, size: dict, run, *, fake_location: bool = True, mobile: bool = False) -> None:
        self.index += 1
        label = f"{self.index:02d}-{name}"
        folder = self.out / f"_{label}"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        context = self.browser.new_context(
            viewport=size,
            record_video_dir=str(folder),
            record_video_size=size,
            device_scale_factor=1,
            is_mobile=mobile,
            has_touch=mobile,
            permissions=["geolocation"] if fake_location else [],
            geolocation=PLACE if fake_location else None,
        )
        context.add_init_script(OVERLAY_JS)
        page = context.new_page()
        started = time.time()
        status = "ok"
        try:
            run(page)
        except Exception as error:  # a scene that cannot finish should not lose the others
            status = "stopped early: " + str(error).strip().splitlines()[0][:140]
        finally:
            self.pace.wait(page, 0.6)
            video = page.video
            context.close()  # the video file is finalised when the context closes
            final = self.out / f"{label}.webm"
            try:
                video.save_as(str(final))
                self.clips.append((final, size))
            except PlaywrightError:
                status += " (no video saved)"
            shutil.rmtree(folder, ignore_errors=True)
        self.report.append((label, f"{status}  [{time.time() - started:.0f}s]"))
        print(f"  {label:<28} {status}")

    # ---------------------------------------------------------------------------------------- small actions

    def caption(self, page, text: str, seconds: float = 2.2) -> None:
        page.evaluate("t => window.__caption && window.__caption(t)", text)
        self.pace.wait(page, seconds)

    def clear_caption(self, page) -> None:
        page.evaluate("() => window.__caption && window.__caption('')")

    def glide(self, page, locator, *, dwell: float = 0.35) -> None:
        locator.scroll_into_view_if_needed(timeout=15000)
        box = locator.bounding_box()
        if not box:
            return
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y, steps=28)
        self.pace.wait(page, dwell)

    def click(self, page, locator, *, dwell: float = 0.35) -> None:
        self.glide(page, locator, dwell=dwell)
        locator.click(timeout=20000)
        self.pace.wait(page, 0.5)

    def type(self, page, locator, text: str) -> None:
        self.glide(page, locator, dwell=0.2)
        locator.click(timeout=15000)
        locator.press_sequentially(text, delay=int(38 * self.pace.speed))
        self.pace.wait(page, 0.4)

    def scroll(self, page, pixels: int, steps: int = 8) -> None:
        for _ in range(steps):
            page.mouse.wheel(0, pixels / steps)
            page.wait_for_timeout(int(90 * self.pace.speed))

    def web_login(self, page, who: tuple[str, str]) -> None:
        page.goto(f"{WEB}/login")
        self.pace.wait(page, 0.8)
        self.type(page, page.get_by_label("Email"), who[0])
        self.type(page, page.get_by_label("Password"), who[1])
        self.click(page, page.get_by_role("button", name="Sign in"))
        page.wait_for_url(lambda url: "/login" not in url, timeout=30000)
        self.pace.wait(page, 1.2)


# ------------------------------------------------------------------------------------------------ helpers


def reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=4)
        return True
    except Exception:
        return False


def make_photo(path: Path) -> Path:
    """A plain PNG (sky, street, a pile of bags) so the demo needs no image file. Pure Python, no Pillow."""
    w, h = 640, 420
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            if y < 190:
                px = (150 + y // 6, 190 + y // 8, 235)  # sky
            elif y < 215:
                px = (160, 160, 155)  # kerb
            else:
                px = (96, 98, 92)  # road
            for cx, cy, r, col in ((250, 300, 46, (60, 120, 70)), (310, 320, 40, (190, 60, 50)), (360, 300, 44, (40, 60, 140)), (290, 270, 34, (230, 230, 225)), (400, 330, 36, (210, 180, 60))):
                if (x - cx) ** 2 + (y - cy) ** 2 < r * r:
                    px = col
            row += bytes(px)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)
    return path


def title_card(page, title: str, subtitle: str, seconds: float, pace: Pace) -> None:
    page.set_content(
        f"""<body style="margin:0;height:100vh;display:grid;place-items:center;background:linear-gradient(135deg,#e6ecff,#fff1e6,#e4f3ff);
        font-family:system-ui,Segoe UI,sans-serif;color:#14213d;text-align:center">
        <div><div style="display:inline-grid;place-items:center;width:88px;height:88px;border-radius:26px;background:#e2621f;color:#fff;font-size:54px;margin-bottom:22px">&#8635;</div>
        <div style="font-size:58px;font-weight:800;letter-spacing:-1px">{title}</div>
        <div style="font-size:24px;color:#5b6478;margin-top:14px;max-width:900px">{subtitle}</div></div></body>"""
    )
    pace.wait(page, seconds)


# ------------------------------------------------------------------------------------------------ the scenes


def scene_resident_web(rec: Recorder, photo: Path):
    def run(page):
        rec.web_login(page, RESIDENT)
        rec.caption(page, "A resident signs in and sees their own reports")
        rec.click(page, page.get_by_role("link", name="Report incident").first)
        page.wait_for_url("**/incidents/new")
        rec.caption(page, "Reporting waste takes a photo, a pin and a few words")
        rec.click(page, page.get_by_role("button", name="Overflowing bins"))
        rec.type(page, page.get_by_label("What did you see?"), " behind the Sector 17 market, spilling onto the footpath")
        rec.click(page, page.get_by_role("button", name="Use my location"))
        page.wait_for_function("document.getElementById('lat') && document.getElementById('lat').value !== ''", timeout=20000)
        rec.pace.wait(page, 1.0)
        rec.glide(page, page.locator("#photo-input"), dwell=0.2)
        page.locator("#photo-input").set_input_files(str(photo))
        page.get_by_alt_text("Attached photo 1").wait_for(timeout=15000)
        rec.caption(page, "The checklist ticks off what, where and photo", 2.4)
        rec.click(page, page.get_by_role("button", name="Submit report"))
        page.wait_for_url(lambda url: "/incidents/" in url and "/new" not in url, timeout=40000)
        rec.state["incident_url"] = page.url
        rec.pace.wait(page, 1.5)
        rec.caption(page, "The report is saved. A supervisor reviews every one before anyone is sent.", 3.0)
        rec.clear_caption(page)

    return run


def scene_supervisor_web(rec: Recorder):
    def run(page):
        rec.web_login(page, SUPERVISOR)
        rec.caption(page, "The supervisor's command center: what needs a decision, and where", 3.0)
        rec.scroll(page, 380)
        rec.pace.wait(page, 1.0)
        page.goto(f"{WEB}/incidents")
        rec.caption(page, "Reports ranked by risk, age and target time", 2.6)
        url = rec.state.get("incident_url")
        if url:
            page.goto(url)
            rec.pace.wait(page, 1.2)
            rec.caption(page, "Open the new report: the photo, the place, the history", 2.4)
            analyse = page.get_by_role("button", name="Run analysis")
            if analyse.count():
                rec.click(page, analyse.first)
                rec.caption(page, "AI reads the photo and scores the hotspot. A person can override it.", 1.5)
                try:
                    page.get_by_text("The AI suggests").wait_for(timeout=75000)
                except PlaywrightTimeout:
                    rec.caption(page, "(AI analysis is not available on this server, so review continues by hand)", 2.5)
            create = page.get_by_role("button", name="Create work order")
            if create.count():
                rec.click(page, create.first)
                rec.click(page, page.get_by_role("button", name="Approve for cleanup").first)
                rec.caption(page, "Approve the work, then give it to one named driver", 2.4)
                page.get_by_label("Assign to").select_option(label=DRIVER_NAME)
                rec.click(page, page.get_by_role("button", name="Assign worker"))
                rec.pace.wait(page, 1.0)
        page.goto(f"{WEB}/routes")
        rec.caption(page, "Route planner: pick a driver, then group that driver's jobs", 2.8)
        rec.click(page, page.get_by_role("button", name="Fill vehicle"))
        rec.click(page, page.get_by_role("button", name="Preview optimised route"))
        page.locator(".preview-card").wait_for(timeout=30000)
        rec.caption(page, "The planner orders the stops. Urgent sites come earlier.", 3.0)
        rec.click(page, page.get_by_role("button", name="Save route"))
        page.wait_for_url("**/routes/**", timeout=30000)
        rec.pace.wait(page, 1.5)
        rec.caption(page, "Approving the route sends it to the driver automatically", 2.6)
        approve = page.get_by_role("button", name="Approve and send")
        if approve.count():
            rec.click(page, approve.first)
            rec.pace.wait(page, 1.2)
        rec.scroll(page, 420)
        rec.caption(page, "The driver can open the whole route in Google Maps for live directions", 2.8)
        page.goto(f"{WEB}/fleet")
        rec.caption(page, "Live fleet: every vehicle, from a crew phone or a GPS tracker", 3.0)
        marker = page.locator(".leaflet-marker-icon, .fleet-marker, [aria-label^='Vehicle']")
        if marker.count():
            rec.click(page, marker.first)
            rec.caption(page, "Select a vehicle to see its recent trail", 2.4)
        rec.clear_caption(page)

    return run


def scene_driver_web(rec: Recorder):
    def run(page):
        rec.web_login(page, DRIVER)
        page.goto(f"{WEB}/work")
        rec.caption(page, "The driver sees their route the moment it is approved", 2.6)
        card = page.get_by_text("Your route").first
        card.wait_for(timeout=20000)
        rec.glide(page, card)
        rec.caption(page, "Stops in order, the next one highlighted, a Navigate link on each", 3.0)
        rec.scroll(page, 360)
        rec.caption(page, "Sharing the vehicle's position puts it on the supervisor's live map", 2.8)
        rec.clear_caption(page)

    return run


def scene_resident_phone(rec: Recorder):
    def run(page):
        page.goto(RESIDENT_APP)
        page.get_by_text("See waste? Report it").wait_for(timeout=30000)
        rec.caption(page, "The resident phone app opens with a short welcome", 2.4)
        rec.click(page, page.get_by_role("button", name="Next"))
        rec.pace.wait(page, 1.0)
        rec.click(page, page.get_by_role("button", name="Next"))
        rec.pace.wait(page, 1.0)
        rec.click(page, page.get_by_role("button", name="Get started"))
        page.get_by_role("button", name="Sign in").wait_for(timeout=15000)
        rec.type(page, page.get_by_label("Email").locator("visible=true").first, RESIDENT[0])
        rec.type(page, page.get_by_label("Password").locator("visible=true").first, RESIDENT[1])
        rec.click(page, page.get_by_role("button", name="Sign in"))
        page.get_by_text("My reports").first.wait_for(timeout=20000)
        rec.caption(page, "My reports: follow each one until it is cleaned", 2.6)
        rec.click(page, page.get_by_text("Report", exact=True).last)
        rec.caption(page, "Report waste with a photo and a pin", 2.6)
        rec.scroll(page, 500)
        rec.click(page, page.get_by_text("Account", exact=True).last)
        rec.pace.wait(page, 1.2)
        rec.clear_caption(page)

    return run


def scene_crew_phone(rec: Recorder):
    def run(page):
        page.goto(CREW_APP)
        page.get_by_text("Your jobs, most urgent first").wait_for(timeout=30000)
        rec.caption(page, "The crew app: jobs, a planned route, live location, proof of work", 2.6)
        rec.click(page, page.get_by_role("button", name="Next"))
        rec.pace.wait(page, 1.0)
        rec.click(page, page.get_by_role("button", name="Next"))
        rec.pace.wait(page, 1.0)
        rec.click(page, page.get_by_role("button", name="Get started"))
        page.get_by_role("button", name="Sign in").wait_for(timeout=15000)
        rec.type(page, page.get_by_label("Email").locator("visible=true").first, DRIVER[0])
        rec.type(page, page.get_by_label("Password").locator("visible=true").first, DRIVER[1])
        rec.click(page, page.get_by_role("button", name="Sign in"))
        page.get_by_text("My jobs").first.wait_for(timeout=20000)
        rec.caption(page, "Today's jobs, with the supervisor's route on top", 2.6)
        route = page.get_by_text("Your route", exact=True).first
        if route.count():
            rec.click(page, route)
            page.get_by_role("button", name="Open the whole route in Google Maps").wait_for(timeout=15000)
            rec.caption(page, "Stop by stop, with Navigate and one tap to open it all in Google Maps", 3.0)
            rec.scroll(page, 520)
            rec.pace.wait(page, 1.0)
            page.go_back()
        rec.click(page, page.get_by_text("Location", exact=True).last)
        rec.caption(page, "Share the vehicle's position so supervisors see it live", 2.8)
        rec.clear_caption(page)

    return run


# ------------------------------------------------------------------------------------------------ joining the clips


def join_clips(clips: list[tuple[Path, dict]], out: Path) -> Path | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not clips:
        return None
    inputs: list[str] = []
    filters: list[str] = []
    for i, (clip, size) in enumerate(clips):
        inputs += ["-i", str(clip)]
        filters.append(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=0xeef1fb,setsar=1,fps=25,format=yuv420p[v{i}]")
    chain = "".join(f"[v{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=0[v]"
    target = out / "demo.mp4"
    command = [ffmpeg, "-y", *inputs, "-filter_complex", ";".join(filters + [chain]), "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", str(target)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print("ffmpeg could not join the clips:\n" + result.stderr[-600:])
        return None
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Record the CivicLoop demo as video.")
    parser.add_argument("--out", default="demo_recording", help="folder for the videos")
    parser.add_argument("--speed", type=float, default=1.0, help="pace: 1.0 normal, 1.5 slower, 0.7 faster")
    parser.add_argument("--no-mobile", action="store_true", help="skip the two phone-app scenes")
    parser.add_argument("--no-join", action="store_true", help="keep separate clips, do not join them with ffmpeg")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    pace = Pace(args.speed)

    if not reachable(f"{API}/health"):
        sys.exit(f"The backend is not answering at {API}. Start it and seed the demo data first (see the top of this file).")
    if not reachable(f"{WEB}/login"):
        sys.exit(f"The web app is not answering at {WEB}. Start it first (npm run dev in frontend/).")
    photo = make_photo(out / "demo-photo.png")

    print(f"Recording to {out}\n")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        rec = Recorder(browser, out, pace)

        rec.scene("title", DESKTOP, lambda page: title_card(page, "CivicLoop", "Report it. Route it. Prove it was cleaned.", 3.5, pace), fake_location=False)
        rec.scene("resident-web", DESKTOP, scene_resident_web(rec, photo))
        rec.scene("supervisor-web", DESKTOP, scene_supervisor_web(rec))
        rec.scene("driver-web", DESKTOP, scene_driver_web(rec))
        if not args.no_mobile:
            if reachable(RESIDENT_APP):
                rec.scene("resident-phone", PHONE, scene_resident_phone(rec), mobile=True)
            else:
                print(f"  (skipping the resident phone app: nothing at {RESIDENT_APP})")
            if reachable(CREW_APP):
                rec.scene("crew-phone", PHONE, scene_crew_phone(rec), mobile=True)
            else:
                print(f"  (skipping the crew phone app: nothing at {CREW_APP})")
        rec.scene("end", DESKTOP, lambda page: title_card(page, "AI suggests. People decide.", "A pilot-ready waste workflow for Indian cities.", 3.5, pace), fake_location=False)
        browser.close()

    print("\nClips:")
    for clip, _ in rec.clips:
        print("  ", clip.name)
    if args.no_join:
        return
    joined = join_clips(rec.clips, out)
    if joined:
        print(f"\nJoined video: {joined}")
    else:
        print("\nffmpeg was not found (or failed), so the clips were left separate. Install ffmpeg to get one demo.mp4.")


if __name__ == "__main__":
    main()
