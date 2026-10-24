"""Pitch 2.0 figures for CivicLoopAI. Run: python scripts/pitch2_figures.py

Writes 16:9 PNGs (2000 x 1125) to docs/pitch2/. It reuses the palette and helpers of scripts/pitch_figures.py and the
vetted data slides of pitch 1 (problem, model scorecard, market, pricing, competitors), and adds the flow charts, route
map, live tracking, security, reliability, product tours and pilot plan.

Rules kept from pitch 1: every number is measured by us (docs/ml_report/metrics.json, the test suite, the code) or typed
in below with its source, and a chart built on simulated data says so on the chart.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

import pitch_figures as p1  # noqa: E402
import pitch_figures_market as p1m  # noqa: E402
from pitch_figures import (  # noqa: E402
    AMBER, BLUE, INK, LINE, M, MUTED, ORANGE, ORANGE_DK, RED, SLATE, TEAL,
    arrow, blank_axes, box, canvas, footer,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "pitch2"
OUT.mkdir(parents=True, exist_ok=True)
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "pitch2_src"  # fresh web screenshots, if present
GREEN_DK = "#177a64"
SOFT = "#f3f5fa"


def save(fig, name: str) -> None:
    fig.savefig(OUT / name, bbox_inches=None)
    plt.close(fig)
    print("wrote", name)


def reuse(function, produced: str, name: str) -> None:
    """Run a pitch-1 slide, but write it into pitch2 under a new name."""
    p1.OUT = OUT
    function()
    (OUT / produced).replace(OUT / name)
    print("   renamed", produced, "->", name)


def chip(ax, x, y, w, h, big, small, col=ORANGE):
    box(ax, x, y, w, h, "", fc="white", ec=col, lw=2.2, r=0.014)
    ax.text(x + w / 2, y + h * 0.62, big, ha="center", va="center", fontsize=26, fontweight="bold", color=col)
    ax.text(x + w / 2, y + h * 0.22, small, ha="center", va="center", fontsize=11.5, color=MUTED, linespacing=1.2)


def node(ax, x, y, w, h, title, sub="", kind="software", fs=12.5):
    """A flow-chart step. software = blue, person = orange, store/result = teal, rule = amber."""
    colours = {"software": ("#eef2fb", BLUE, BLUE), "person": ("#fff1e8", ORANGE, ORANGE_DK), "result": ("#e8f6f2", TEAL, GREEN_DK), "rule": ("#fff6dc", AMBER, "#8a6100"), "plain": (SOFT, LINE, INK)}
    fc, ec, tc = colours[kind]
    box(ax, x, y, w, h, "", fc=fc, ec=ec, lw=2)
    if sub:
        ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=12.5, fontweight="bold", color=tc, linespacing=1.15)
        ax.text(x + w / 2, y + h * 0.27, sub, ha="center", va="center", fontsize=9.6, color=INK, linespacing=1.2)
    else:
        ax.text(x + w / 2, y + h / 2, title, ha="center", va="center", fontsize=fs, fontweight="bold", color=tc, linespacing=1.15)


def legend(ax, y=0.035, items=(("a person decides or does it", "#fff1e8", ORANGE), ("software does or suggests", "#eef2fb", BLUE), ("a rule the server enforces", "#fff6dc", AMBER), ("an outcome", "#e8f6f2", TEAL))):
    x = 0.05
    for text, fc, ec in items:
        box(ax, x, y, 0.016, 0.026, fc=fc, ec=ec, r=0.004)
        ax.text(x + 0.024, y + 0.013, text, va="center", fontsize=11.5)
        x += 0.07 + 0.0085 * len(text)


def crop_phone(path: Path, aspect: float = 844 / 390) -> Image.Image:
    img = Image.open(path).convert("RGB")
    want_h = int(img.width * aspect)
    return img.crop((0, 0, img.width, min(img.height, want_h)))


def place_image(fig, img: Image.Image, cx: float, top: float, width_in: float, radius_in: float = 0.0, frame: str | None = None, label: str | None = None):
    """Draw an image whose centre is at figure fraction cx and whose top edge is at figure fraction `top`."""
    fw, fh = fig.get_size_inches()
    w_frac = width_in / fw
    h_frac = width_in * img.height / img.width / fh
    ax = fig.add_axes([cx - w_frac / 2, top - h_frac, w_frac, h_frac])
    ax.imshow(img, aspect="auto")
    ax.axis("off")
    if frame:
        # an outline drawn around the picture, in axes space
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False, ec=frame, lw=3, clip_on=False))
    if label:
        fig.text(cx, top - h_frac - 0.012, label, ha="center", va="top", fontsize=12.5, fontweight="bold")
    return ax, h_frac


def phone_frame(fig, cx, top, width_in, img, label):
    """A phone-shaped bezel with the screen inside."""
    fw, fh = fig.get_size_inches()
    pad_in = 0.07
    bw = (width_in + 2 * pad_in) / fw
    bh = (width_in * img.height / img.width + 2 * pad_in) / fh
    ax = fig.add_axes([cx - bw / 2, top - bh, bw, bh])
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.09", transform=ax.transAxes, fc=INK, ec=INK))
    inner = fig.add_axes([cx - width_in / 2 / fw, top - bh + pad_in / fh, width_in / fw, width_in * img.height / img.width / fh])
    # round the screen corners with a mask
    arr = np.asarray(img.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    r = int(w * 0.075)
    yy, xx = np.ogrid[:h, :w]
    mask = np.ones((h, w), bool)
    for cy_, cx_ in ((r, r), (r, w - r - 1), (h - r - 1, r), (h - r - 1, w - r - 1)):
        corner = ((yy - cy_) ** 2 + (xx - cx_) ** 2) > r * r
        region = ((yy < r) | (yy > h - r - 1)) & ((xx < r) | (xx > w - r - 1))
        quad = (np.abs(yy - cy_) <= r) & (np.abs(xx - cx_) <= r)
        mask &= ~(corner & region & quad)
    arr[~mask, 3] = 0
    inner.imshow(arr, aspect="auto")
    inner.axis("off")
    fig.text(cx, top - bh - 0.012, label, ha="center", va="top", fontsize=12.5, fontweight="bold")


def browser_frame(fig, cx, top, width_in, img, label):
    fw, fh = fig.get_size_inches()
    bar_in = 0.22
    h_in = width_in * img.height / img.width
    ax = fig.add_axes([cx - width_in / 2 / fw, top - (h_in + bar_in) / fh, width_in / fw, (h_in + bar_in) / fh])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.012", fc="#e9ecf4", ec=LINE, lw=1.2))
    for i, c in enumerate(("#ff6b5e", "#ffc13d", "#3fcf5d")):
        ax.add_patch(plt.Circle(((0.018 + i * 0.016), 1 - bar_in / (h_in + bar_in) / 2), 0.0055, color=c, transform=ax.transAxes))
    inner = fig.add_axes([cx - width_in / 2 / fw, top - (h_in + bar_in) / fh, width_in / fw, h_in / fh])
    inner.imshow(img, aspect="auto")
    inner.axis("off")
    fig.text(cx, top - (h_in + bar_in) / fh - 0.01, label, ha="center", va="top", fontsize=12.5, fontweight="bold")


# ============================================================================================ 00 cover
def cover():
    from civicloop.api import create_app  # counts what is really there

    routes = len({(r.path, tuple(sorted(r.methods or ()))) for r in create_app(database_url="sqlite://", auth_secret="x" * 40).routes if getattr(r, "path", "").startswith("/api/v1")})
    fig = plt.figure(figsize=(13.33, 7.5), dpi=150)
    fig.patch.set_facecolor("white")
    ax = blank_axes(fig)
    ax.add_patch(plt.Circle((0.93, 0.98), 0.28, color="#ffd9c2", alpha=0.7, lw=0))
    ax.add_patch(plt.Circle((0.02, 0.05), 0.25, color="#d7e3ff", alpha=0.7, lw=0))
    ax.add_patch(FancyBboxPatch((0.06, 0.64), 0.075, 0.133, boxstyle="round,pad=0,rounding_size=0.022", fc=ORANGE, ec=ORANGE_DK, lw=2))
    ax.text(0.0975, 0.7065, "↻", ha="center", va="center", fontsize=44, color="white", fontweight="bold")
    ax.text(0.155, 0.74, "CivicLoop", fontsize=48, fontweight="bold", va="center")
    ax.text(0.06, 0.55, "Report it. Route it. Prove it was cleaned.", fontsize=30, color=INK, va="center")
    ax.text(0.06, 0.47, "A waste-management workflow for Indian cities where software suggests\nand a person decides, and nothing is closed without a photo.", fontsize=17, color=MUTED, va="center", linespacing=1.45)
    stats = [("4", "roles: resident, crew,\nsupervisor, admin"), ("3", "apps: web, resident phone\napp, crew phone app"), (f"{routes}", "API routes, all role-checked\nand city-scoped"), ("118", "automated backend tests,\nall passing")]
    for i, (big, small) in enumerate(stats):
        chip(ax, 0.06 + i * 0.2275, 0.14, 0.2, 0.2, big, small, col=[ORANGE, BLUE, TEAL, SLATE][i])
    ax.text(0.06, 0.075, "Pilot city: Chandigarh   •   built for many cities from day one   •   Pitch 2.0", fontsize=12.5, color=MUTED)
    save(fig, "00_cover.png")


# ============================================================================================ 02 journey
def journey():
    fig = canvas("From a photo on a phone to a clean street", "The whole job in nine steps. Each one is a screen in the product, not a slide idea.")
    ax = blank_axes(fig)
    steps = [
        ("1  Report", "Resident adds a photo\nand a pin", "person"),
        ("2  Understand", "AI reads the photo,\nscores the hotspot", "software"),
        ("3  Review", "Supervisor checks,\napproves or rejects", "person"),
        ("4  Assign", "Job goes to one\nnamed driver", "person"),
        ("5  Route", "Planner orders that\ndriver's jobs", "software"),
        ("6  Send", "Supervisor approves,\nroute lands in the\ndriver's app", "person"),
        ("7  Drive", "Google Maps guides;\nvehicle position is live", "software"),
        ("8  Prove", "Driver sends an\nafter-photo", "person"),
        ("9  Verify", "Supervisor reviews;\nonly then it is closed", "person"),
    ]
    cols = 5
    w, h = 0.165, 0.2
    for i, (title, sub, kind) in enumerate(steps):
        row, col = divmod(i, cols)
        x = 0.05 + col * 0.1875 if row == 0 else 0.1425 + col * 0.1875
        y = 0.52 if row == 0 else 0.2
        node(ax, x, y, w, h, title, sub, kind)
        if i < len(steps) - 1:
            nrow, ncol = divmod(i + 1, cols)
            if nrow == row:
                arrow(ax, (x + w + 0.002, y + h / 2), (x + 0.1875 - 0.002, y + h / 2), color=INK, lw=2.2)
    # wrap arrow from the end of row 1 to the start of row 2
    ax.annotate("", xy=(0.1425 + w / 2, 0.2 + h + 0.004), xytext=(0.05 + 4 * 0.1875 + w / 2, 0.52 - 0.004), arrowprops=dict(arrowstyle="-|>", color=INK, lw=2.2, connectionstyle="angle3,angleA=-90,angleB=0"))
    ax.text(0.5, 0.455, "", fontsize=1)
    ax.text(0.5, 0.83, "", fontsize=1)
    legend(ax, 0.125, (("a person decides or does it", "#fff1e8", ORANGE), ("software does or suggests", "#eef2fb", BLUE)))
    footer(fig, "Every step above exists in the running product today. The AI step needs a Gemini key (or an open-weight model); without one, analysis is switched off and supervisors review by hand.")
    save(fig, "02_journey.png")


# ============================================================================================ 03 swimlanes
def swimlanes():
    fig = canvas("Who does what, step by step", "Swim-lane flow of one report, from the first photo to a verified cleanup")
    ax = blank_axes(fig)
    lanes = [("Resident", ORANGE, 0.715), ("Driver\n(crew)", TEAL, 0.565), ("Software", BLUE, 0.415), ("Supervisor", ORANGE_DK, 0.265)]
    for name, col, y in lanes:
        box(ax, 0.04, y - 0.07, 0.92, 0.14, "", fc="#fafbfd", ec=LINE, r=0.006, lw=1.2)
        box(ax, 0.04, y - 0.07, 0.095, 0.14, "", fc=col, ec=col, r=0.006)
        ax.text(0.0875, y, name, ha="center", va="center", fontsize=12, color="white", fontweight="bold", linespacing=1.2)
    lane_y = {n.replace("\n", " "): y for n, _, y in lanes}
    X0, PITCH, W, H = 0.15, 0.0905, 0.082, 0.1

    def n(col, lane, text, kind):
        x, y = X0 + col * PITCH, lane_y[lane]
        node(ax, x, y - H / 2, W, H, text, "", kind, fs=10)
        return dict(x=x, y=y)

    a = n(0, "Resident", "Report:\nphoto + pin", "person")
    b = n(1, "Software", "AI rating,\nduplicates", "software")
    c = n(2, "Supervisor", "Review,\napprove", "person")
    d = n(3, "Supervisor", "Assign to\none driver", "person")
    e = n(4, "Software", "Plan that\ndriver's route", "software")
    f = n(5, "Supervisor", "Preview,\napprove", "person")
    g = n(6, "Driver (crew)", "Route in\ndriver's app", "result")
    h = n(7, "Driver (crew)", "Drive, share\nposition", "person")
    i = n(8, "Driver (crew)", "Finish +\nafter-photo", "person")
    j = n(8, "Software", "Check the\nphoto is new", "software")
    k = n(8, "Supervisor", "Verify:\nclosed", "result")

    def elbow(p, q, col=INK, lw=1.8):
        x1, y1 = p["x"] + W + 0.002, p["y"]
        x2, y2 = q["x"] - 0.002, q["y"]
        if abs(y1 - y2) < 1e-6:
            arrow(ax, (x1, y1), (x2, y2), color=col, lw=lw)
            return
        xm = (x1 + x2) / 2
        ax.plot([x1, xm, xm], [y1, y1, y2], color=col, lw=lw, solid_capstyle="round")
        arrow(ax, (xm, y2), (x2, y2), color=col, lw=lw)

    def drop(p, q, col=INK, lw=1.8):
        up = q["y"] > p["y"]
        arrow(ax, (p["x"] + W / 2, p["y"] + (H / 2 + 0.002) * (1 if up else -1)), (q["x"] + W / 2, q["y"] - (H / 2 + 0.002) * (1 if up else -1)), color=col, lw=lw)

    elbow(a, b)
    elbow(b, c)
    elbow(c, d)
    elbow(d, e)
    elbow(e, f)
    elbow(f, g, col=GREEN_DK, lw=2.6)
    elbow(g, h)
    elbow(h, i)
    drop(i, j)
    drop(j, k)
    ax.text(X0 + 5.5 * PITCH + W / 2, 0.37, "approving sends it,\nautomatically", fontsize=10, color=GREEN_DK, ha="center", va="center", style="italic", fontweight="bold")
    ax.text(0.5, 0.135, "Unclear or rejected at review? The supervisor asks for more detail or closes it with a reason. A report never moves forward by hand.", ha="center", fontsize=12, color=MUTED)
    ax.text(0.5, 0.095, "Orange = a person decides or does it   •   blue = software   •   green = an outcome", ha="center", fontsize=11.5, color=MUTED)
    save(fig, "03_swimlanes.png")


# ============================================================================================ 04 state machines
def state_machines():
    fig = canvas("Three status trails, all guarded by the server", "Nothing can be pushed forward by hand: each move comes from its own action, and each one is logged")
    ax = blank_axes(fig)

    def trail(y, title, steps, who, col):
        ax.text(0.05, y + 0.09, title, fontsize=16, fontweight="bold", color=col)
        n = len(steps)
        w = 0.88 / n - 0.02
        for i, s in enumerate(steps):
            x = 0.05 + i * (w + 0.02)
            box(ax, x, y - 0.035, w, 0.085, s, fc=col, ec=col, tc="white", fs=11.5, bold=True, r=0.012)
            ax.text(x + w / 2, y - 0.055, who[i], ha="center", va="top", fontsize=9.6, color=MUTED, style="italic")
            if i < n - 1:
                arrow(ax, (x + w + 0.002, y + 0.0075), (x + w + 0.018, y + 0.0075), color=INK, lw=1.8)

    trail(0.70, "Report", ["Pending\nanalysis", "Ready for\nreview", "Approved", "In progress", "Resolved", "Verified"], ["on creation", "AI + risk score", "supervisor", "driver starts", "driver + photo", "supervisor"], BLUE)
    trail(0.46, "Work order", ["Draft", "Approved", "Assigned", "In progress", "Completed"], ["supervisor opens", "supervisor", "to one driver", "driver", "driver"], ORANGE)
    trail(0.22, "Route", ["Draft", "Approved\n= sent to driver", "Driver works\nthe stops", "All stops\ndone"], ["one driver only", "supervisor", "progress follows the jobs", "route closes itself"], TEAL)
    box(ax, 0.05, 0.035, 0.9, 0.085, "", fc="#fff6dc", ec=AMBER, r=0.008)
    ax.text(0.5, 0.0775, "Side exits: Uncertain (needs more detail), Rejected (with a reason), Reopened (verification refused the photo), Cancelled.\nA second live work order for one incident is impossible while one exists: the database enforces it with a unique index.", ha="center", va="center", fontsize=11, linespacing=1.5)
    save(fig, "04_status_trails.png")


# ============================================================================================ 05 driver route flow
def driver_route_flow():
    fig = canvas("One route belongs to one driver", "The route rule, and what happens when the supervisor approves")
    ax = blank_axes(fig)
    node(ax, 0.05, 0.62, 0.17, 0.15, "Jobs assigned\nto Karan", "approved, assigned,\nnot on a route yet", "person")
    node(ax, 0.05, 0.37, 0.17, 0.15, "Jobs assigned\nto Ravi", "kept apart: a route\ncannot mix drivers", "person")
    node(ax, 0.29, 0.5, 0.17, 0.2, "Planner", "pick a driver, pick\nthat driver's jobs,\ncapacity and depot", "person")
    node(ax, 0.53, 0.5, 0.17, 0.2, "OR-Tools orders\nthe stops", "urgent sites pulled\nearlier; 2 s limit;\nstraight-line km", "software")
    node(ax, 0.77, 0.5, 0.18, 0.2, "Draft route", "saved for the\nsupervisor only;\nthe driver sees nothing", "plain")
    node(ax, 0.77, 0.2, 0.18, 0.2, "Approve", "checks jobs are still\nthis driver's and live", "rule")
    node(ax, 0.53, 0.2, 0.17, 0.2, "Appears in the\ndriver's app", "ordered stops, next\nstop, progress", "result")
    node(ax, 0.29, 0.2, 0.17, 0.2, "Google Maps", "whole route as\nwaypoints, live\nturn by turn", "software")
    node(ax, 0.05, 0.2, 0.17, 0.12, "Progress", "stops tick off as\njobs are completed", "result")
    arrow(ax, (0.222, 0.695), (0.29, 0.62), color=INK, lw=2)
    arrow(ax, (0.222, 0.445), (0.29, 0.56), color=LINE, lw=1.6)
    ax.text(0.226, 0.505, "✕", fontsize=15, color=RED, ha="center", fontweight="bold")
    arrow(ax, (0.462, 0.6), (0.528, 0.6), color=INK, lw=2)
    arrow(ax, (0.702, 0.6), (0.768, 0.6), color=INK, lw=2)
    arrow(ax, (0.86, 0.498), (0.86, 0.402), color=INK, lw=2)
    arrow(ax, (0.768, 0.3), (0.702, 0.3), color=GREEN_DK, lw=3)
    arrow(ax, (0.528, 0.3), (0.462, 0.3), color=INK, lw=2)
    arrow(ax, (0.288, 0.3), (0.224, 0.27), color=INK, lw=2)
    ax.text(0.735, 0.34, "sent\nautomatically", fontsize=10, color=GREEN_DK, ha="center", va="center", fontweight="bold")
    rules = ["Only jobs already assigned to a driver can be routed", "Mixed drivers are refused, with their names", "A draft is invisible to the driver", "Approve fails if a job finished or moved meanwhile", "A job can be on only one approved route"]
    box(ax, 0.05, 0.035, 0.9, 0.1, "", fc=SOFT, ec=LINE)
    ax.text(0.065, 0.118, "Rules enforced in the server (7 tests):", fontsize=11.5, fontweight="bold", va="top")
    ax.text(0.065, 0.088, "   •   ".join(rules[:3]), fontsize=10.2, va="top")
    ax.text(0.065, 0.06, "   •   ".join(rules[3:]), fontsize=10.2, va="top")
    save(fig, "05_driver_route.png")


# ============================================================================================ 06 route map
def route_map():
    from civicloop.demo import DEPOT, SITES
    from civicloop.engines.routing import RouteEngine, RouteEngineConfig

    def attempt(seed):
        rng = random.Random(seed)
        picks = rng.sample(range(len(SITES)), 10)
        orders, incidents = [], {}
        for k, idx in enumerate(picks):
            d, lat, lon, sev, _ = SITES[idx]
            oid = f"o{k}"
            incidents[f"i{k}"] = SimpleNamespace(latitude=lat, longitude=lon)
            orders.append(SimpleNamespace(id=oid, incident_id=f"i{k}", estimated_volume=1.5, priority={"high": 80, "medium": 50}.get(sev, 30)))
        result = RouteEngine(RouteEngineConfig(priority_weight=0.1)).build(orders, incidents, 30, DEPOT)
        return orders, incidents, result

    # the baseline is the nearest-stop-next rule (what the model scorecard compares against); pick a layout whose
    # saving is close to the measured average rather than the best one we can find
    for seed in range(1, 200):
        orders, incidents, result = attempt(seed)
        saving_try = (result.greedy_distance_km - result.distance_km) / result.greedy_distance_km * 100
        if 10 <= saving_try <= 13 and any(o.priority >= 70 for o in orders):
            break
    coords = {o.id: (incidents[o.incident_id].latitude, incidents[o.incident_id].longitude) for o in orders}
    by_id = {o.id: o for o in orders}
    pick_order = list(result.greedy_order)
    pick_km = result.greedy_distance_km
    best = [s.work_order_id for s in result.stops]

    fig = canvas("What the planner does with ten jobs", "Ten demo sites in Chandigarh. Left: the nearest-stop-next rule. Right: the order the planner chose.")
    for k, (ax_rect, seq, km, title, col) in enumerate(
        (([0.05, 0.2, 0.42, 0.58], pick_order, pick_km, "Nearest stop next", SLATE), ([0.53, 0.2, 0.42, 0.58], best, result.distance_km, "Planned by OR-Tools", ORANGE))
    ):
        ax = fig.add_axes(ax_rect)
        pts = [DEPOT] + [coords[i] for i in seq] + [DEPOT]
        ys, xs = zip(*pts)
        ax.plot(xs, ys, color=col, lw=2.6, alpha=0.9, zorder=2, solid_joinstyle="round")
        for a, b in zip(pts[:-1], pts[1:]):
            ax.annotate("", xy=((a[1] + b[1]) / 2 + (b[1] - a[1]) * 0.02, (a[0] + b[0]) / 2 + (b[0] - a[0]) * 0.02), xytext=((a[1] + b[1]) / 2, (a[0] + b[0]) / 2), arrowprops=dict(arrowstyle="-|>", color=col, lw=0), zorder=3)
        for n, oid in enumerate(seq, 1):
            lat, lon = coords[oid]
            urgent = by_id[oid].priority >= 70
            ax.scatter(lon, lat, s=520 if urgent else 380, color=RED if urgent else "white", edgecolor=col, linewidth=2.4, zorder=4)
            ax.text(lon, lat, str(n), ha="center", va="center", fontsize=12.5, fontweight="bold", color="white" if urgent else INK, zorder=5)
        ax.scatter(DEPOT[1], DEPOT[0], marker="s", s=330, color=INK, zorder=5)
        ax.text(DEPOT[1], DEPOT[0] - 0.0028, "depot", ha="center", va="top", fontsize=10.5, color=INK, fontweight="bold")
        ax.set_title(f"{title}: {km:.1f} km", loc="left", fontsize=17, fontweight="bold", color=col)
        ax.set_aspect(1 / math.cos(math.radians(30.7)))
        ax.grid(color="#eef0f6", lw=1)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(LINE)
    saving = (pick_km - result.distance_km) / pick_km * 100
    fig.text(0.5, 0.135, f"{saving:.0f}% shorter on this example, and urgent (red) stops come earlier.", ha="center", fontsize=17, fontweight="bold", color=ORANGE_DK)
    fig.text(0.5, 0.098, "We chose a layout near the measured average (8 to 16% across 12 random layouts per size, next slide). One example is an illustration, not a promise.", ha="center", fontsize=12.5, color=MUTED)
    footer(fig, "Computed by civicloop/engines/routing.py on 10 of the 16 demo sites in civicloop/demo.py (layout picked to be typical, not the best); straight-line distances, not road distances. Red = priority 70 or higher.")
    save(fig, "06_route_example.png")


# ============================================================================================ 08 live tracking
def live_tracking():
    from civicloop.demo import DEPOT, SITES

    rng = random.Random(3)
    fig = canvas("See every vehicle, live", "Phone GPS from the crew app, or a hardware tracker, into one fleet map")
    # a simulated drive: straight legs between sites with a stop at each, speed colouring
    stops = [DEPOT] + [(s[1], s[2]) for s in SITES[:7]] + [DEPOT]
    pts, speeds = [], []
    for a, b in zip(stops[:-1], stops[1:]):
        steps = 14
        for t in range(steps):
            f = t / steps
            pts.append((a[0] + (b[0] - a[0]) * f + rng.uniform(-0.0002, 0.0002), a[1] + (b[1] - a[1]) * f + rng.uniform(-0.0002, 0.0002)))
            speeds.append(max(0, 22 + 14 * math.sin(f * math.pi) + rng.uniform(-3, 3)) if 1 < t < steps - 1 else rng.uniform(0, 4))
    ax = fig.add_axes([0.05, 0.2, 0.5, 0.56])
    xs = np.array([p[1] for p in pts])
    ys = np.array([p[0] for p in pts])
    segs = np.stack([np.column_stack([xs[:-1], ys[:-1]]), np.column_stack([xs[1:], ys[1:]])], axis=1)
    lc = LineCollection(segs, array=np.array(speeds[:-1]), cmap="RdYlGn", linewidths=5, zorder=2)
    ax.add_collection(lc)
    ax.scatter(xs[-1], ys[-1], s=600, color=INK, zorder=4)
    ax.scatter(xs[40], ys[40], s=900, marker="o", color="white", edgecolor=ORANGE, linewidth=4, zorder=5)
    ax.text(xs[40], ys[40], "▲", ha="center", va="center", fontsize=15, color=ORANGE, zorder=6)
    ax.annotate("Demo truck 1\n24 km/h, moving", (xs[40], ys[40]), (xs[40] + 0.006, ys[40] + 0.0035), fontsize=12.5, fontweight="bold", arrowprops=dict(arrowstyle="-", color=INK), bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=LINE))
    ax.set_xlim(xs.min() - 0.004, xs.max() + 0.012)
    ax.set_ylim(ys.min() - 0.003, ys.max() + 0.004)
    ax.set_aspect(1 / math.cos(math.radians(30.7)))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(color="#eef0f6")
    for s in ax.spines.values():
        s.set_color(LINE)
    cb = fig.colorbar(lc, ax=ax, orientation="horizontal", fraction=0.04, pad=0.03, aspect=40)
    cb.set_label("speed, km/h (red = stopped, green = driving)", fontsize=11)
    ax.set_title("Today's trail, simulated drive", loc="left", fontsize=14, fontweight="bold")

    ax2 = fig.add_axes([0.6, 0.0, 0.37, 1.0])
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis("off")
    ax2.text(0.0, 0.78, "How a fix is trusted", fontsize=15, fontweight="bold", va="top")
    chain = [("Phone (crew app) or\nhardware tracker", "person"), ("Plausibility filter", "rule"), ("Vehicle row + 7-day trail", "result"), ("Fleet map and\nhistory", "software")]
    for i, (t, k) in enumerate(chain):
        y = 0.64 - i * 0.135
        node(ax2, 0.0, y - 0.05, 0.62, 0.095, t, "", k)
        if i < len(chain) - 1:
            arrow(ax2, (0.31, y - 0.052), (0.31, y - 0.095), color=INK, lw=1.8)
    ax2.text(0.66, 0.48, "drops:\n• over 160 km/h\n• 5 min in the future\n• older than 24 h\n• accuracy over 500 m\n• a jump no truck\n   can make", fontsize=9.6, va="center", color=INK, linespacing=1.35)
    for i, (state, colr, note) in enumerate((("moving", TEAL, ""), ("idle", AMBER, ""), ("stale", "#c26a00", ""), ("offline", SLATE, ""))):
        ax2.scatter(0.04 + i * 0.24, 0.13, s=330, color=colr, transform=ax2.transAxes, clip_on=False)
        ax2.text(0.04 + i * 0.24, 0.095, state, ha="center", va="top", fontsize=11, fontweight="bold")
    footer(fig, "The trail is simulated in the style of civicloop/gps_sim.py (straight legs between demo sites, with stops): real tracking has not yet been run on a phone or a hardware tracker. Rules from civicloop/services/fleet.py.")
    save(fig, "08_live_tracking.png")


# ============================================================================================ 09 architecture
def architecture():
    fig = canvas("How it is built (today)", "One API, role-gated and city-scoped, behind a web proxy; small engines you can swap; recoverable background work")
    ax = blank_axes(fig)
    clients = [("Resident app\nExpo, iOS + Android", ORANGE), ("Crew app\nExpo, iOS + Android", AMBER), ("Web app\nNext.js, any role", BLUE), ("GPS tracker\nX-Device-Key", SLATE)]
    for i, (t, c) in enumerate(clients):
        box(ax, 0.05 + i * 0.2325, 0.725, 0.2125, 0.085, t, fc=c, ec=c, tc="white", fs=12.5, bold=True)
    box(ax, 0.05, 0.615, 0.9, 0.07, "Web proxy: sign-in token kept in an httpOnly cookie, cross-site writes refused. Phones talk to the API directly with a token in secure storage.", fc=SOFT, fs=11.5)
    box(ax, 0.05, 0.435, 0.9, 0.15, "", fc="#fff1e8", ec=ORANGE, lw=2)
    ax.text(0.5, 0.556, "API: FastAPI   (78 routes)", ha="center", fontsize=16, fontweight="bold", color=ORANGE_DK)
    guards = ["rate limits on sign-in", "role check on every route", "queries limited to one city", "retry-safe report creation", "audit log of every change"]
    for i, g in enumerate(guards):
        box(ax, 0.065 + i * 0.1755, 0.45, 0.165, 0.065, g, fc="white", ec=ORANGE, fs=10.3, r=0.01)
    engines = [("Photo analysis\nGemini 2.5 Flash", BLUE), ("Duplicates\nbge-small embeddings", BLUE), ("Hotspot risk\ntrained per city", BLUE), ("Routes\nGoogle OR-Tools", BLUE), ("Rules\nverify, priority, fleet", SLATE)]
    for i, (t, c) in enumerate(engines):
        box(ax, 0.05 + i * 0.185, 0.265, 0.165, 0.11, t, fc="white", ec=c, fs=11.3, lw=2)
    ax.text(0.05, 0.395, "Engines (each can be swapped without touching the rest)", fontsize=12, color=MUTED)
    stores = [("Database\nSQLite now, Postgres ready;\nforeign keys + migrations", SLATE), ("Photo storage\nlocal or S3-style;\ntype checked by content", SLATE), ("Job queue + recovery\nin-process or Redis;\nlost jobs re-queued", SLATE), ("Models per city\nwritten atomically", SLATE)]
    for i, (t, c) in enumerate(stores):
        box(ax, 0.05 + i * 0.2325, 0.085, 0.2125, 0.12, t, fc="#eef0f6", ec=LINE, fs=10.6)
    ax.text(0.05, 0.222, "State", fontsize=12, color=MUTED)
    for x in (0.16, 0.39, 0.62, 0.85):
        arrow(ax, (x, 0.725), (x, 0.69), lw=1.2)
    arrow(ax, (0.5, 0.615), (0.5, 0.587), lw=1.6)
    arrow(ax, (0.5, 0.435), (0.5, 0.38), lw=1.6)
    arrow(ax, (0.5, 0.265), (0.5, 0.208), lw=1.6)
    footer(fig, "Route count taken from the running app. SQLite is for development and demos; the production switch (CIVICLOOP_ENV=production) refuses in-memory storage or queue and an out-of-date database.")
    save(fig, "09_architecture.png")


# ============================================================================================ 10 security layers
def security():
    fig = canvas("Six layers between a request and your data", "Found by a written risk review (FMEA) of the whole codebase, then fixed and tested")
    ax = blank_axes(fig)
    layers = [
        ("1  At the door", "Sign-in throttled (8 wrong tries / 5 min); sign-up throttled; sign-in token in an httpOnly cookie; cross-site writes refused; uploads checked by their bytes", BLUE),
        ("2  Who you are", "scrypt passwords; signed tokens; role and active state read from the database on every call; \"sign out everywhere\" ends all sessions; platform-admin emails cannot be claimed", ORANGE),
        ("3  Which city", "Every read filtered and every write stamped by city; a request session cannot drop its city scope by accident; disabled cities are locked out; a city must be switched off before a merge", TEAL),
        ("4  What is allowed", "State machines enforced in the server; one live work order per incident; imports cannot skip steps; one route per driver; the last admin cannot be removed", AMBER),
        ("5  What is stored", "Foreign keys on; WAL and lock wait; unique keys for retries; photos by real type; schema version checked at start in production", SLATE),
        ("6  What happened", "Audit log of every change; jobs recovered after a crash; models written safely; failures logged, not swallowed", GREEN_DK),
    ]
    for i, (title, text, col) in enumerate(layers):
        y = 0.7 - i * 0.108
        w = 0.9 - i * 0.02
        x = 0.05 + i * 0.01
        box(ax, x, y, w, 0.092, "", fc="white", ec=col, lw=2.4, r=0.012)
        box(ax, x, y, 0.16, 0.092, "", fc=col, ec=col, r=0.012)
        ax.text(x + 0.08, y + 0.046, title, ha="center", va="center", fontsize=13.5, fontweight="bold", color="white")
        import textwrap

        ax.text(x + 0.175, y + 0.046, textwrap.fill(text, 112), va="center", fontsize=10.4, linespacing=1.35)
    footer(fig, "Not claimed: a third-party penetration test, email verification for ordinary sign-ups, row-level security in the database, or a content-security policy. Details and what is still open: docs/FMEA.md.")
    save(fig, "10_security_layers.png")


# ============================================================================================ 11 roles matrix
def roles_matrix():
    fig = canvas("Four roles, one clear set of powers", "What each person can do. Pages and buttons follow this table, and the server enforces it.")
    caps = [
        "Report waste with photo and pin", "See own reports and their progress", "See every report in the city", "Review, approve, reject a report",
        "Open and assign work orders", "Plan and approve routes", "See assigned jobs and own route", "Start, finish, send proof",
        "Share vehicle location", "See the live fleet", "Verify cleanup evidence", "Manage people and roles", "Platform: cities and merges",
    ]
    roles = ["Resident", "Driver", "Supervisor", "City admin", "Platform\nadmin"]
    # 2 = yes, 1 = partly / own only, 0 = no
    grid = [
        [2, 2, 2, 2, 2], [2, 2, 2, 2, 2], [0, 2, 2, 2, 2], [0, 0, 2, 2, 2], [0, 0, 2, 2, 2], [0, 0, 2, 2, 2], [0, 2, 0, 0, 0],
        [0, 2, 0, 0, 0], [0, 2, 0, 0, 0], [0, 0, 2, 2, 2], [0, 0, 2, 2, 2], [0, 0, 0, 2, 2], [0, 0, 0, 0, 2],
    ]
    ax = fig.add_axes([0.3, 0.15, 0.65, 0.63])
    cmap = {0: "#f1f3f8", 1: "#ffe8b0", 2: "#bfe6da"}
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            ax.add_patch(FancyBboxPatch((c + 0.06, len(grid) - r - 1 + 0.12), 0.88, 0.76, boxstyle="round,pad=0,rounding_size=0.12", fc=cmap[v], ec="none"))
            ax.text(c + 0.5, len(grid) - r - 0.5, {0: "", 1: "own", 2: "✓"}[v], ha="center", va="center", fontsize=15 if v == 2 else 11, color=GREEN_DK if v == 2 else "#8a6100", fontweight="bold")
    ax.set_xlim(0, 5)
    ax.set_ylim(0, len(grid))
    ax.set_xticks([i + 0.5 for i in range(5)], roles, fontsize=12.5, fontweight="bold")
    ax.xaxis.tick_top()
    ax.set_yticks([len(grid) - i - 0.5 for i in range(len(grid))], caps, fontsize=12)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    fig.text(0.05, 0.095, "✓ allowed.  A driver sees the jobs and the vehicle assigned to them; a resident sees only their own reports.", fontsize=11.5, color=MUTED)
    footer(fig, "Derived from the role gates in civicloop/routes_ops.py, routes_fleet.py and api.py (STAFF, SUPERVISOR, WORKER sets). Platform admin = a city admin whose email is listed in CIVICLOOP_PLATFORM_ADMINS.")
    save(fig, "11_roles.png")


# ============================================================================================ 12 mobile tour
def mobile_tour():
    d = ROOT / "docs" / "mobile"
    fig = canvas("Two phone apps, built for the street", "Real app screens against the real backend. Residents report; drivers get a route and navigate.")
    items = [
        ("resident/00-welcome-1.png", "Welcome", "A short intro the\nfirst time it opens"),
        ("resident/06-report-filled.png", "Report with a photo", "Photo, pin, a few words,\nsent in under a minute"),
        ("resident/07-report-detail.png", "Follow it to done", "Status, photos and map\nuntil it is cleaned"),
        ("crew/02-jobs-todo.png", "Today's jobs", "Your route on top,\nmost urgent jobs below"),
        ("crew/11-route.png", "Route, stop by stop", "Next stop, progress,\nopen it all in Google Maps"),
        ("crew/06-location-sharing.png", "Share the vehicle", "Supervisors see where\nthe vehicle is, live"),
    ]
    w_in = 1.72
    pitch = (w_in + 0.14) + 0.13
    left = 0.6
    for i, (rel, label, caption) in enumerate(items):
        img = crop_phone(d / rel)
        x_in = left + i * pitch + (0.4 if i >= 3 else 0) + (w_in + 0.14) / 2
        cx = x_in / 13.33
        phone_frame(fig, cx, 0.745, w_in, img, label)
        fig.text(cx, 0.745 - (w_in * img.height / img.width + 0.14) / 7.5 - 0.058, caption, ha="center", va="top", fontsize=10.5, color=MUTED, linespacing=1.35)
    fig.text((left + 1.5 * pitch + 0.0) / 13.33 + 0.045, 0.805, "Residents", fontsize=16, fontweight="bold", color=ORANGE_DK, ha="center")
    fig.text((left + 4.5 * pitch + 0.4) / 13.33 + 0.045, 0.805, "Drivers (crew)", fontsize=16, fontweight="bold", color=GREEN_DK, ha="center")
    footer(fig, "Screens are the app's web build in a phone-sized browser, not photos of a handset: the map is OpenStreetMap tiles and the glass blur is drawn by the browser. Built with Expo (React Native); unit tests and tests against the live API pass.")
    save(fig, "12_mobile_tour.png")


# ============================================================================================ 13 web tour
def web_tour():
    fig = canvas("One web console for the control room", "Supervisors and admins on a desktop; the same pages work on a phone")
    files = [
        ("dashboard.png", "Dashboard: what needs a decision"), ("routes-planner.png", "Route planner: one driver at a time"),
        ("route-detail.png", "Approved route, sent to the driver"), ("live-fleet.png", "Live fleet map"),
    ]
    for i, (name, label) in enumerate(files):
        path = SHOTS / name
        if not path.exists():
            path = ROOT / "docs" / "screenshots" / "03-supervisor" / name
        img = Image.open(path).convert("RGB")
        img = img.crop((0, 0, img.width, min(img.height, int(img.width * 0.43))))
        row, col = divmod(i, 2)
        browser_frame(fig, 0.27 + col * 0.46, 0.81 - row * 0.37, 5.4, img, label)
    footer(fig, "Real pages from the running Next.js app, with the Chandigarh demo data. Screenshots of every page and role are in docs/screenshots/.")
    save(fig, "13_web_tour.png")


# ============================================================================================ 14 reliability
def reliability():
    fig = canvas("We audited ourselves, then fixed it", "FMEA: every way the system could fail, scored by severity x likelihood x how late we would notice (RPN)")
    items = [  # (id, label, rpn, status)  status: F fixed, P partly, M you must act
        ("F-01", "No limit on sign-in guesses", 392, "F"), ("F-02", "Jobs stuck or lost after a crash", 384, "F"), ("F-03", "Database locks, foreign keys off", 336, "F"),
        ("F-04", "Photos and jobs lost on restart", 324, "F"), ("F-05", "Admin address could be claimed", 320, "F"), ("F-06", "Code newer than the database", 320, "F"),
        ("F-07", "One retry froze all jobs", 294, "F"), ("F-08", "AI call could hang forever", 280, "F"), ("F-09", "City isolation could fail open", 216, "F"),
        ("F-10", "Import could skip the work flow", 210, "F"), ("F-11", "Upload type trusted by label", 210, "F"), ("F-12", "Retry made duplicate reports", 210, "F"),
        ("F-16", "Dashboard read whole tables", 180, "P"), ("F-24", "API key shared in chat", 135, "M"),
    ]
    ax = fig.add_axes([0.3, 0.16, 0.38, 0.62])
    colour = {"F": TEAL, "P": AMBER, "M": RED}
    for i, (fid, label, rpn, st) in enumerate(items[::-1]):
        ax.barh(i, rpn, color=colour[st], height=0.68, zorder=2)
        ax.text(rpn + 6, i, str(rpn), va="center", fontsize=11.5, fontweight="bold")
    ax.set_yticks(range(len(items)), [f"{fid}  {label}" for fid, label, *_ in items[::-1]], fontsize=11)
    ax.set_xlim(0, 450)
    ax.set_xticks([])
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.tick_params(left=False)
    ax.set_title("Highest-risk findings", loc="left", fontsize=14, fontweight="bold")
    for k, (txt, col) in enumerate((("fixed", TEAL), ("partly fixed", AMBER), ("needs the owner", RED))):
        fig.patches.append(plt.Rectangle((0.3 + k * 0.1, 0.1), 0.01, 0.02, transform=fig.transFigure, fc=col, ec=col))
        fig.text(0.315 + k * 0.1, 0.11, txt, fontsize=11, va="center")

    ax2 = fig.add_axes([0.73, 0.4, 0.22, 0.38])
    sizes = [32, 3, 1, 1]
    cols = [TEAL, AMBER, RED, "#b9c0d0"]
    ax2.pie(sizes, colors=cols, startangle=90, counterclock=False, wedgeprops=dict(width=0.38, edgecolor="white", linewidth=2))
    ax2.text(0, 0.06, "37", ha="center", va="center", fontsize=36, fontweight="bold")
    ax2.text(0, -0.2, "findings", ha="center", va="center", fontsize=12, color=MUTED)
    fig.text(0.84, 0.355, "32 fixed   3 partly\n1 needs a key rotation\n1 withdrawn (was wrong)", ha="center", va="top", fontsize=11.5, linespacing=1.5)
    fig.text(0.84, 0.23, "Backend tests: 93 → 118", ha="center", fontsize=13.5, fontweight="bold", color=GREEN_DK)
    fig.text(0.84, 0.19, "Migrations 0001 to 0007 build\nthe schema from scratch", ha="center", va="top", fontsize=11.5, color=MUTED, linespacing=1.4)
    footer(fig, "From docs/FMEA.md (37 findings, scored 1 to 10 on each factor; static review, not a penetration test). The status of each fix and what is still open are in section 0 of that file.")
    save(fig, "14_reliability.png")


# ============================================================================================ 15 quality scoreboard
def scoreboard():
    fig = canvas("Checked, not just built", "What has been run, and what has not")
    ax = blank_axes(fig)
    tiles = [
        ("118", "backend tests pass", "API, roles, cities, routes,\nfleet, jobs, hardening", TEAL),
        ("15 + 5", "phone-app tests pass", "15 unit, 5 against the live API", TEAL),
        ("7", "database migrations", "build the schema from an\nempty database", TEAL),
        ("0", "type errors", "web + 5 phone-app packages", TEAL),
        ("2", "phone apps bundle", "Android and iOS, both apps", TEAL),
        ("112", "browser checks pass", "every page and role; 6 older\nflows still to update", TEAL),
    ]
    for i, (big, title, sub, col) in enumerate(tiles):
        row, c = divmod(i, 3)
        x, y = 0.05 + c * 0.3167, 0.55 - row * 0.27
        box(ax, x, y, 0.2867, 0.24, "", fc="white", ec=col, lw=2.2, r=0.014)
        ax.text(x + 0.0143 * 2, y + 0.165, big, fontsize=32, fontweight="bold", color=col, va="center")
        ax.text(x + 0.0143 * 2, y + 0.095, title, fontsize=14, fontweight="bold", va="center")
        ax.text(x + 0.0143 * 2, y + 0.045, sub, fontsize=10.5, color=MUTED, va="center", linespacing=1.25)
    box(ax, 0.05, 0.075, 0.9, 0.14, "", fc="#fff6dc", ec=AMBER, r=0.01)
    ax.text(0.5, 0.145, "Not yet done, said plainly:\nreal-phone testing (background GPS, camera permissions, native maps)  •  load testing\na measured accuracy for the photo AI  •  a real city's data", ha="center", va="center", fontsize=12.5, color="#6b4a00", fontweight="bold", linespacing=1.5)
    footer(fig, "Counts from the last runs in this repository. Browser checks: the latest full run of frontend/e2e/check.mjs, 112 passed and 6 failed; the 6 are older scripted flows written before the one-route-per-driver rule.")
    save(fig, "15_scoreboard.png")


# ============================================================================================ 16 roles of AI
def humans_and_ai():
    fig = canvas("AI suggests. People decide.", "Where software helps, and where a person always has the last word")
    ax = blank_axes(fig)
    rows = [
        ("Read the photo", "Category and severity from Gemini 2.5 Flash", "Supervisor can override, or send it back", "AI"),
        ("Spot repeat reports", "Sentence embeddings group look-alikes nearby", "Supervisor confirms or rejects the group", "AI"),
        ("Rank hotspots", "Per-city model, used only if it beats the formula", "Supervisor sets priority by hand, with a reason", "AI"),
        ("Order the stops", "OR-Tools plans one driver's round", "Supervisor previews, then approves", "AI"),
        ("Approve work", "-", "Supervisor only", "P"),
        ("Close a report", "Checks the after-photo is a new file", "Supervisor verifies; nothing closes by hand", "P"),
    ]
    box(ax, 0.05, 0.755, 0.9, 0.05, "", fc=INK, ec=INK, r=0.008)
    for x, t in ((0.06, "Step"), (0.27, "What the software does"), (0.6, "What a person controls")):
        ax.text(x, 0.78, t, color="white", fontsize=12.5, fontweight="bold", va="center")
    for i, (a, b, c, k) in enumerate(rows):
        y = 0.65 - i * 0.108
        box(ax, 0.05, y, 0.9, 0.095, "", fc=("#eef2fb" if k == "AI" else "#fff1e8"), ec="none", r=0.008)
        ax.text(0.06, y + 0.0475, a, fontsize=13.5, fontweight="bold", va="center")
        ax.text(0.27, y + 0.0475, b, fontsize=11, va="center", color=BLUE if k == "AI" else MUTED)
        ax.text(0.6, y + 0.0475, c, fontsize=11, va="center", color=ORANGE_DK, fontweight="bold")
    footer(fig, "From the code: civicloop/services/analysis.py, duplicates, hotspot_risk.py (ml), engines/routing.py, services/work_order.py, verification.py. The after-photo check compares file content, not what the picture shows: an image-based check is a pilot item.")
    save(fig, "16_humans_and_ai.png")


# ============================================================================================ 20 pilot plan
def pilot_plan():
    fig = canvas("An 8-week pilot to prove it", "One ward, one supervisor team, real reports. Targets are proposals, not results.")
    ax = fig.add_axes([0.37, 0.2, 0.58, 0.56])
    tasks = [
        ("Set up the city, accounts, vehicles", 0, 1, SLATE),
        ("Train supervisors and crews", 0.5, 1.5, SLATE),
        ("Residents report; supervisors review", 1, 8, ORANGE),
        ("Assign drivers, plan and send routes", 2, 8, BLUE),
        ("Live tracking on pilot vehicles", 2, 8, TEAL),
        ("Hand-label 300 photos to measure the AI", 3, 6, AMBER),
        ("Retrain risk on real reports; ship only if better", 6, 8, AMBER),
        ("Review with the city, write up results", 7.2, 8, INK),
    ]
    for i, (name, a, b, col) in enumerate(tasks[::-1]):
        ax.barh(i, b - a, left=a, color=col, height=0.62, zorder=2)
    ax.set_yticks(range(len(tasks)), [t[0] for t in tasks[::-1]], fontsize=11.5)
    ax.set_xlim(0, 8)
    ax.set_xticks(range(0, 9), [f"wk {i}" if i else "start" for i in range(9)], fontsize=11)
    ax.grid(axis="x", color="#eef0f6", zorder=0)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False)
    fig.text(0.05, 0.12, "What we would measure:  hours from report to cleaned  •  repeat-site rate  •  km per round vs the city's own logs\n% of closures with verified proof  •  photo-AI accuracy on labelled photos", fontsize=12, color=INK, linespacing=1.6)
    footer(fig, "The 8-week length and the 300-photo sample are our suggestion and are not agreed with any city. No pilot has been run yet.")
    save(fig, "20_pilot_plan.png")


# ============================================================================================ 21 roadmap
def roadmap():
    fig = canvas("What is built, and what comes next", "Honest status. Built means running and tested today.")
    ax = blank_axes(fig)
    cols = [
        ("Built", TEAL, ["Report, review, assign, route, verify", "One route per driver, sent on approval", "Google Maps hand-off for drivers", "Live vehicle tracking (phone or tracker)", "Many cities, platform admin", "Web + resident + crew apps", "Risk review with fixes and tests"]),
        ("Pilot (next 2 months)", ORANGE, ["Run in one real ward", "Test background GPS on real phones", "Measure the photo AI on 300 real photos", "Road-distance routes, real fuel logs", "Push notifications for new routes", "Email verification for sign-ups"]),
        ("Later", BLUE, ["Image-based after-photo check", "Bulk-generator compliance module", "RFID / weighbridge import", "WhatsApp reporting", "Content-security policy, pen test", "Offline mode for crews"]),
    ]
    for i, (head, col, items) in enumerate(cols):
        x = 0.05 + i * 0.3167
        box(ax, x, 0.73, 0.2867, 0.07, head, fc=col, ec=col, tc="white", fs=16, bold=True)
        for j, t in enumerate(items):
            box(ax, x, 0.635 - j * 0.092, 0.2867, 0.075, t, fc="white", ec=col, fs=11.3, lw=1.8, r=0.01)
    footer(fig, "Gaps listed under Later are also called out in docs/pitch/competitors.md. Dates are plans, not commitments.")
    save(fig, "21_roadmap.png")


# ============================================================================================ 22 go to market
def go_to_market():
    fig = canvas("How we get from a pilot to revenue", "Our plan over twelve months. Order follows what is easiest to start, not the biggest prize.")
    ax = blank_axes(fig)
    steps = [
        ("Months 0 to 3", "City pilot, no fee", "One ward, 90 days.\nGoal: real results\nand a case study.", SLATE),
        ("Months 3 to 6", "City licence", "Rs 1 lakh + Rs 250 a\nvehicle a month.\nPilot fee credited.", BLUE),
        ("Months 4 to 9", "Contractors", "Rs 400 a vehicle a month.\nProof-of-service photos\nfor the paying city.", ORANGE),
        ("Months 8 to 12", "Bulk generators", "Rs 12k to 30k a site a year.\nNeeds a compliance\nmodule (not built yet).", TEAL),
    ]
    for i, (when, what, note, col) in enumerate(steps):
        x = 0.05 + i * 0.2325
        w = 0.2125
        h = 0.12 + i * 0.035
        box(ax, x, 0.28, w, 0.38 + i * 0.035, "", fc="white", ec=col, lw=2.4, r=0.014)
        box(ax, x, 0.58 + i * 0.035, w, 0.08, when, fc=col, ec=col, tc="white", fs=13, bold=True, r=0.014)
        ax.text(x + w / 2, 0.52 + i * 0.035, what, ha="center", fontsize=17, fontweight="bold", color=col)
        ax.text(x + w / 2, 0.42, note, ha="center", va="center", fontsize=11.5, color=MUTED, linespacing=1.4)
        if i < 3:
            arrow(ax, (x + w + 0.002, 0.45), (x + 0.2325 - 0.002, 0.45), color=INK, lw=2.2)
    ax.text(0.5, 0.17, "Not our first move: state tenders (lowest bid wins, mostly GPS hardware)\nand a paid consumer app (a free government app already covers reporting).", ha="center", fontsize=12, color=MUTED, linespacing=1.5)
    footer(fig, "Prices are proposals from docs/pitch/market-and-pricing.md; the scores behind this order are our judgement, not a measurement. Nobody has agreed to pay yet.")
    save(fig, "22_go_to_market.png")


# ============================================================================================ 23 the ask
def the_ask():
    fig = plt.figure(figsize=(13.33, 7.5), dpi=150)
    ax = blank_axes(fig)
    ax.add_patch(plt.Circle((0.95, 0.98), 0.3, color="#ffd9c2", alpha=0.7, lw=0))
    ax.add_patch(plt.Circle((0.0, 0.0), 0.3, color="#d7e3ff", alpha=0.7, lw=0))
    ax.text(0.06, 0.86, "What we are asking for", fontsize=36, fontweight="bold", va="center")
    ax.text(0.06, 0.77, "A chance to prove it with one real city, with a person at every decision.", fontsize=19, color=MUTED, va="center")
    asks = [("1", "One ward, 8 weeks", "A pilot with a city or a contractor, with real reports and real vehicles."), ("2", "A little data and access", "Existing vehicle logs and collection records, to compare routes honestly."), ("3", "A named supervisor team", "Five to ten people to use it daily and tell us what is wrong.")]
    for i, (n, t, s) in enumerate(asks):
        y = 0.6 - i * 0.16
        ax.scatter(0.09, y + 0.04, s=2600, color=ORANGE, transform=ax.transAxes)
        ax.text(0.09, y + 0.04, n, ha="center", va="center", fontsize=24, color="white", fontweight="bold")
        ax.text(0.15, y + 0.065, t, fontsize=21, fontweight="bold", va="center")
        ax.text(0.15, y + 0.015, s, fontsize=14, color=MUTED, va="center")
    box(ax, 0.06, 0.07, 0.88, 0.13, "", fc=INK, ec=INK, r=0.012)
    ax.text(0.5, 0.135, "In return: a working product today, an honest scorecard,\nand a written plan for what we will measure.", ha="center", va="center", fontsize=15, color="white", fontweight="bold", linespacing=1.5)
    save(fig, "23_the_ask.png")


def main() -> None:
    cover()
    reuse(p1.problem, "01_problem.png", "01_problem.png")
    journey()
    swimlanes()
    state_machines()
    driver_route_flow()
    route_map()
    reuse(p1.routes, "06_routes.png", "07_route_results.png")
    live_tracking()
    architecture()
    security()
    roles_matrix()
    mobile_tour()
    web_tour()
    reliability()
    scoreboard()
    humans_and_ai()
    reuse(p1.scorecard, "07_scorecard.png", "17_model_scorecard.png")
    reuse(p1m.feasibility, "09_feasibility.png", "18_market_feasibility.png")
    reuse(p1m.pricing, "10_pricing.png", "19_pricing.png")
    pilot_plan()
    roadmap()
    go_to_market()
    reuse(p1m.competitors, "11_competitors.png", "24_competitors.png")
    the_ask()


if __name__ == "__main__":
    main()
