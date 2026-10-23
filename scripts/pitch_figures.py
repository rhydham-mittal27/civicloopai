"""Pitch figures for CivicLoopAI. Run: python scripts/pitch_figures.py

Writes 16:9 PNGs to docs/pitch/. Every number is either read from docs/ml_report/metrics.json (our own
measurements) or typed in below with its source. Nothing is invented: charts built on simulated or
hand-written data say so on the chart.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "pitch"
OUT.mkdir(parents=True, exist_ok=True)
M = json.loads((ROOT / "docs" / "ml_report" / "metrics.json").read_text(encoding="utf-8"))

INK, MUTED, LINE = "#14213d", "#5b6478", "#d9deea"
ORANGE, ORANGE_DK = "#e2621f", "#a63500"
BLUE, TEAL, AMBER, RED, SLATE = "#2563a8", "#1f9d82", "#e0a100", "#c8372d", "#5b6b8c"
PAPER = "#ffffff"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 15,
        "axes.edgecolor": LINE,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "figure.facecolor": PAPER,
        "axes.facecolor": PAPER,
        "savefig.facecolor": PAPER,
    }
)


def canvas(title: str, subtitle: str | None = None):
    fig = plt.figure(figsize=(13.33, 7.5), dpi=150)
    fig.text(0.05, 0.93, title, fontsize=27, fontweight="bold", va="top")
    if subtitle:
        fig.text(0.05, 0.865, subtitle, fontsize=15, color=MUTED, va="top")
    return fig


def footer(fig, text: str):
    text = textwrap.fill(" ".join(text.split()), 150)
    fig.text(0.05, 0.025, text, fontsize=10, color=MUTED, va="bottom", linespacing=1.4)


def save(fig, name: str):
    fig.savefig(OUT / name, bbox_inches=None)
    plt.close(fig)
    print("wrote", name)


def box(ax, x, y, w, h, text="", fc="#f3f5fa", ec=LINE, tc=INK, fs=13, bold=False, r=0.012, lw=1.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, fontweight="bold" if bold else "normal", linespacing=1.3)


def arrow(ax, p, q, color=MUTED, lw=1.8, style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=16, color=color, lw=lw, connectionstyle=f"arc3,rad={rad}"))


def blank_axes(fig):
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return ax


# ------------------------------------------------------------------------------------------ 1. problem
def problem():
    fig = canvas("Collection works. What happens next does not.", "Share of the waste generated, 2021-22, as reported to the Central Pollution Control Board")
    # national: generated 170,339 TPD
    ax = fig.add_axes([0.16, 0.20, 0.30, 0.54])
    labels = ["Collected", "Processed or\ntreated", "Sanitary\nlandfill", "Unmanaged\ngap"]
    vals = [92, 54, 24, 22]
    cols = [SLATE, TEAL, AMBER, RED]
    bars = ax.barh(labels[::-1], vals[::-1], color=cols[::-1], height=0.62)
    for b, v in zip(bars, vals[::-1]):
        ax.text(v + 1.5, b.get_y() + b.get_height() / 2, f"{v}%", va="center", fontsize=18, fontweight="bold")
    ax.set_xlim(0, 118)
    ax.set_title("India, all states: 170,339 t a day", loc="left", fontsize=16, fontweight="bold", pad=14)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(left=False, labelsize=14)
    ax.set_xticks([])

    ax2 = fig.add_axes([0.64, 0.20, 0.30, 0.54])
    labels2 = ["Collected", "Processed or\ntreated", "Landfilled"]
    vals2 = [100, 83 / 540 * 100, 486 / 540 * 100]
    bars = ax2.barh(labels2[::-1], vals2[::-1], color=[AMBER, TEAL, SLATE], height=0.62)
    for b, v, raw in zip(bars, vals2[::-1], ["486 t/day", "83 t/day", "540 t/day"]):
        ax2.text(v + 1.5, b.get_y() + b.get_height() / 2, f"{v:.0f}%  ({raw})", va="center", fontsize=17, fontweight="bold")
    ax2.set_xlim(0, 175)
    ax2.set_title("Chandigarh: 540 tonnes a day", loc="left", fontsize=16, fontweight="bold", pad=14)
    ax2.spines[["top", "right", "left"]].set_visible(False)
    ax2.tick_params(left=False, labelsize=14)
    ax2.set_xticks([])
    fig.text(0.64, 0.145, "All of it collected, 9 tenths landfilled.", fontsize=13, color=ORANGE_DK, fontweight="bold")
    footer(
        fig,
        "Source: CPCB, Annual Report on Solid Waste Management 2021-22 (cpcb.gov.in/uploads/MSW/MSW_AnnualReport_2021-22.pdf), Table 1 and text. Figures are as submitted by states and UTs. "
        "For Chandigarh the report's processed and landfilled figures add up to more than the amount generated (it marks the row with a footnote). Local reports of the city's processing plant differ; see docs/pitch/README.md.",
    )
    save(fig, "01_problem.png")


# ------------------------------------------------------------------------------------------ 2. loop
def loop():
    fig = canvas("One loop, with a person at every decision", "Observe, understand, predict, prioritise, act, verify, learn")
    ax = blank_axes(fig)
    stages = [
        ("Observe", "Residents and crews\nreport with photo + pin", "person"),
        ("Understand", "Gemini reads the photo:\ncategory, severity", "ai"),
        ("Predict", "Hotspot risk and repeat\nsites from past reports", "ai"),
        ("Prioritise", "Queue ranked by risk,\nage and target time", "ai"),
        ("Act", "Supervisor approves, crew\nis assigned a planned route", "person"),
        ("Verify", "After-photo and a\nsupervisor sign-off", "person"),
        ("Learn", "Outcomes retrain the risk\nmodel, per city", "ai"),
    ]
    cx, cy, rx, ry = 0.5, 0.45, 0.335, 0.285
    n = len(stages)
    for i, (name, desc, kind) in enumerate(stages):
        ang = np.pi / 2 - 2 * np.pi * i / n
        x, y = cx + rx * np.cos(ang) * 1.05, cy + ry * np.sin(ang)
        human = kind == "person"
        w, h = 0.2, 0.135
        box(ax, x - w / 2, y - h / 2, w, h, fc=("#fff1e8" if human else "#eef2fb"), ec=(ORANGE if human else BLUE), lw=2.2)
        ax.text(x, y + 0.03, f"{i + 1}  {name}", ha="center", va="center", fontsize=16, fontweight="bold", color=(ORANGE_DK if human else BLUE))
        ax.text(x, y - 0.026, desc, ha="center", va="center", fontsize=10.5, color=INK, linespacing=1.25)
        ang2 = np.pi / 2 - 2 * np.pi * (i + 1) / n
        x2, y2 = cx + rx * np.cos(ang2) * 1.05, cy + ry * np.sin(ang2)
        v = np.array([x2 - x, y2 - y])
        v = v / np.linalg.norm(v)
        arrow(ax, (x + v[0] * 0.115, y + v[1] * 0.085), (x2 - v[0] * 0.115, y2 - v[1] * 0.085), rad=-0.18)
    ax.text(cx, cy + 0.02, "CivicLoop", ha="center", fontsize=30, fontweight="bold")
    ax.text(cx, cy - 0.035, "AI suggests.\nPeople decide.", ha="center", va="top", fontsize=17, color=MUTED, linespacing=1.4)
    box(ax, 0.05, 0.03, 0.017, 0.028, fc="#fff1e8", ec=ORANGE, r=0.004)
    ax.text(0.075, 0.044, "a person decides or does it", va="center", fontsize=12.5)
    box(ax, 0.3, 0.03, 0.017, 0.028, fc="#eef2fb", ec=BLUE, r=0.004)
    ax.text(0.325, 0.044, "software suggests, a person can override", va="center", fontsize=12.5)
    save(fig, "02_loop.png")


# ------------------------------------------------------------------------------------------ 3. lifecycle
def lifecycle():
    fig = canvas("Nothing is closed without evidence", "How a report moves, and who is allowed to move it")
    ax = blank_axes(fig)
    y = 0.57
    steps = [
        ("Pending\nanalysis", "Report received", SLATE, "system"),
        ("Ready for\nreview", "AI rated it,\nrisk scored", BLUE, "AI"),
        ("Approved", "Supervisor approves,\nwork order opened", ORANGE, "supervisor"),
        ("In progress", "Crew starts\nthe job", AMBER, "worker"),
        ("Resolved", "Crew marks it done\nwith an after-photo", TEAL, "worker"),
        ("Verified", "Supervisor reviews\nthe evidence", "#177a64", "supervisor"),
    ]
    w, h, gap = 0.125, 0.15, 0.027
    x0 = 0.05
    centres = []
    for i, (name, note, col, who) in enumerate(steps):
        x = x0 + i * (w + gap)
        centres.append(x + w / 2)
        box(ax, x, y, w, h, fc=col, ec=col, r=0.014)
        ax.text(x + w / 2, y + h / 2, name, ha="center", va="center", fontsize=15, fontweight="bold", color="white", linespacing=1.15)
        ax.text(x + w / 2, y - 0.03, note, ha="center", va="top", fontsize=11, color=INK, linespacing=1.25)
        ax.text(x + w / 2, y + h + 0.03, who, ha="center", fontsize=11.5, color=MUTED, style="italic")
        if i < len(steps) - 1:
            arrow(ax, (x + w + 0.003, y + h / 2), (x + w + gap - 0.003, y + h / 2), color=INK, lw=2)
    rx = centres[1]
    box(ax, 0.1, 0.2, 0.17, 0.085, "Uncertain\nasks for more detail", fc="#fff6dc", ec=AMBER, fs=12)
    box(ax, 0.3, 0.2, 0.15, 0.085, "Rejected\nwith a reason", fc="#fdecea", ec=RED, fs=12)
    arrow(ax, (rx - 0.055, y), (0.16, 0.285), color=AMBER, lw=1.8, style="<|-|>")
    arrow(ax, (rx + 0.055, y), (0.37, 0.285), color=RED, lw=1.8)
    ax.text(0.05, 0.165, "A supervisor can send a report to either, or back for review.\nThey can never push one forward by hand.", fontsize=11.5, color=MUTED, va="top", linespacing=1.4)
    gx = 0.52
    box(ax, gx, 0.115, 0.43, 0.215, fc="#f3f5fa", ec=LINE)
    ax.text(gx + 0.02, 0.305, "Guard rails, enforced in the server", fontsize=13.5, fontweight="bold", va="top")
    rails = [
        "Approval and progress only come from the work-order flow",
        "Verified needs a finished job and an after-photo",
        "that is not the same file as the before-photo",
        "Every step is written to the audit log",
    ]
    for i, r in enumerate(rails):
        ax.text(gx + 0.02, 0.255 - i * 0.034, ("•  " if i != 2 else "    ") + r, fontsize=11, va="top")
    footer(fig, "From civicloop/api.py (MANUAL_TRANSITIONS) and civicloop/services/verification.py. The after-photo check compares file content, not what the photo shows: an image-based check is not built yet.")
    save(fig, "03_lifecycle.png")


# ------------------------------------------------------------------------------------------ 4. architecture
def architecture():
    fig = canvas("How it is built", "One API, role-gated and city-scoped, in front of small replaceable engines")
    ax = blank_axes(fig)
    # people
    people = [("Resident", ORANGE), ("Crew", AMBER), ("Supervisor", BLUE), ("City admin", SLATE), ("Platform admin", INK)]
    for i, (p, c) in enumerate(people):
        box(ax, 0.05 + i * 0.185, 0.745, 0.165, 0.07, p, fc=c, ec=c, tc="white", fs=14, bold=True)
    box(ax, 0.05, 0.615, 0.9, 0.085, "Web app: Next.js. Pages and navigation follow the role, so people only see what they can use. Works on a phone.", fc="#f3f5fa", fs=13)
    box(ax, 0.05, 0.47, 0.9, 0.105, "", fc="#fff1e8", ec=ORANGE, lw=2)
    ax.text(0.5, 0.548, "API: FastAPI", ha="center", fontsize=16, fontweight="bold", color=ORANGE_DK)
    ax.text(0.5, 0.503, "role check on every route   •   every query limited to the caller's city   •   audit trail on every change", ha="center", fontsize=12.5)
    engines = [
        ("Photo analysis\nGemini 2.5 Flash", BLUE),
        ("Duplicate match\nbge-small embeddings", BLUE),
        ("Hotspot risk\nlogistic / boosted trees", BLUE),
        ("Route planner\nGoogle OR-Tools", BLUE),
        ("Rules\nverification, priority", SLATE),
    ]
    for i, (t, c) in enumerate(engines):
        box(ax, 0.05 + i * 0.185, 0.29, 0.165, 0.115, t, fc="white", ec=c, fs=11.5, lw=2)
    ax.text(0.05, 0.425, "Engines (each can be swapped without touching the rest)", fontsize=12.5, color=MUTED)
    stores = [("Database\nSQLite now, Postgres ready", SLATE), ("Photo storage\nlocal or S3-style", SLATE), ("Job queue\nin-process or Redis", SLATE), ("Per-city model files", SLATE)]
    for i, (t, c) in enumerate(stores):
        box(ax, 0.05 + i * 0.2325, 0.115, 0.2125, 0.1, t, fc="#eef0f6", ec=LINE, fs=11.5)
    ax.text(0.05, 0.235, "State", fontsize=12.5, color=MUTED)
    for x in (0.13, 0.31, 0.5, 0.69, 0.87):
        arrow(ax, (x, 0.745), (x, 0.70), lw=1.2)
    arrow(ax, (0.5, 0.615), (0.5, 0.575), lw=1.6)
    arrow(ax, (0.5, 0.47), (0.5, 0.405), lw=1.6)
    arrow(ax, (0.5, 0.29), (0.5, 0.222), lw=1.6)
    save(fig, "04_architecture.png")


# ------------------------------------------------------------------------------------------ 5. tenancy
def tenancy():
    fig = canvas("Every city is its own workspace", "Add a city by registering in it. Nobody sees another city's data.")
    ax = blank_axes(fig)
    box(ax, 0.05, 0.69, 0.9, 0.095, "Platform admin: confirm real cities, merge a misspelt one, switch into any city to help", fc=INK, ec=INK, tc="white", fs=14, bold=True)
    cities = [("Chandigarh", "160017", ORANGE), ("Pune", "411001", BLUE), ("Jaipur", "302001", TEAL)]
    for i, (c, pin, col) in enumerate(cities):
        x = 0.05 + i * 0.3167
        box(ax, x, 0.17, 0.2667, 0.46, "", fc="white", ec=col, lw=2.6, r=0.02)
        ax.text(x + 0.133, 0.585, c, ha="center", fontsize=21, fontweight="bold", color=col)
        ax.text(x + 0.133, 0.545, f"pincodes from {pin}", ha="center", fontsize=11.5, color=MUTED)
        for j, t in enumerate(["people and roles", "reports and photos", "work orders and routes", "audit log and jobs", "its own risk model"]):
            box(ax, x + 0.02, 0.45 - j * 0.058, 0.2267, 0.044, t, fc="#f3f5fa", ec="#f3f5fa", fs=11.5, r=0.008)
        arrow(ax, (x + 0.133, 0.69), (x + 0.133, 0.63), color=col, lw=1.6, style="<|-|>")
    box(ax, 0.05, 0.065, 0.9, 0.06, "", fc="#f3f5fa", ec=LINE)
    ax.text(0.5, 0.095, "One rule in one place: a row belongs to a city, and every read and write is checked against it. Proven by 18 isolation tests.", ha="center", va="center", fontsize=12.5)
    save(fig, "05_tenancy.png")


# ------------------------------------------------------------------------------------------ 6. routes
def routes():
    fig = canvas("Shorter rounds, and urgent sites sooner", "Measured: planned route vs the nearest-stop-next rule, random layouts, straight-line distance")
    r = M["routing"]
    sizes = ["10", "20", "30"]
    pure = [r[s]["pure_saving_pct_mean"] for s in sizes]
    prio = [r[s]["priority_saving_pct_mean"] for s in sizes]
    ax = fig.add_axes([0.08, 0.25, 0.46, 0.52])
    x = np.arange(3)
    ax.axhspan(4.8, 11, color="#eef2fb", zorder=0, label="Range other city studies report (4.8% to 11%)")
    b1 = ax.bar(x - 0.19, pure, 0.36, color=SLATE, label="Shortest tour", zorder=2)
    b2 = ax.bar(x + 0.19, prio, 0.36, color=ORANGE, label="With urgent-site pull (the default)", zorder=2)
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.35, f"{b.get_height():.1f}%", ha="center", fontsize=13, fontweight="bold")
    ax.set_xticks(x, [f"{s} stops" for s in sizes], fontsize=14)
    ax.set_ylabel("Shorter than nearest-stop-next (%)")
    ax.set_ylim(0, 21)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=11)

    ax2 = fig.add_axes([0.64, 0.25, 0.31, 0.52])
    g = [r[s]["urgent_stop_position_greedy"] for s in sizes]
    p = [r[s]["urgent_stop_position_priority"] for s in sizes]
    for i in range(3):
        ax2.plot([g[i], p[i]], [i, i], color=LINE, lw=3, zorder=1)
        ax2.scatter(g[i], i, s=190, color=SLATE, zorder=2)
        ax2.scatter(p[i], i, s=190, color=ORANGE, zorder=2)
        ax2.text(p[i] - 0.015, i + 0.22, f"{p[i]:.2f}", ha="right", fontsize=12, color=ORANGE_DK, fontweight="bold")
        ax2.text(g[i] + 0.015, i + 0.22, f"{g[i]:.2f}", ha="left", fontsize=12, color=SLATE, fontweight="bold")
    ax2.set_yticks(range(3), [f"{s} stops" for s in sizes], fontsize=14)
    ax2.set_xlim(0.25, 0.65)
    ax2.set_ylim(-0.6, 2.7)
    ax2.set_xlabel("Where urgent stops fall in the round\n(0 = first, 1 = last)")
    ax2.set_title("Urgent sites are reached earlier", loc="left", fontsize=15, fontweight="bold")
    ax2.spines[["top", "right"]].set_visible(False)
    footer(
        fig,
        "Source: our measurements, scripts/ml_report.py, 12 random layouts per size, about 2 s solve time. Straight-line distance, not road distance, and layouts are random rather than real streets. "
        "Other studies (not ours): 4.8% less distance in Ghana (pure.ug.edu.gh); about 8% in Sydney (researchers.westernsydney.edu.au). The band marks that range for comparison.",
    )
    save(fig, "06_routes.png")


# ------------------------------------------------------------------------------------------ 7. ml scorecard
def scorecard():
    fig = canvas("What the models can and cannot do yet", "Honest scorecard. No real city data exists yet, so every test below uses simulated or hand-written data.")
    seeds = M["risk"]["per_seed"]
    ax = fig.add_axes([0.17, 0.27, 0.34, 0.5])
    order = sorted(range(len(seeds)), key=lambda i: max(seeds[i]["logistic"], seeds[i]["gbm"]) - seeds[i]["formula"])
    for row, i in enumerate(order):
        s = seeds[i]
        best = max(s["logistic"], s["gbm"])
        win = best - s["formula"] >= 0.01
        ax.plot([s["formula"], best], [row, row], color=(TEAL if win else LINE), lw=3.5, zorder=1)
        ax.scatter(s["formula"], row, s=110, color=SLATE, zorder=2, label="Hand-set formula" if row == 0 else None)
        ax.scatter(best, row, s=110, color=(TEAL if win else AMBER), zorder=2)
    ax.scatter([], [], s=110, color=TEAL, label="Trained model, clearly better")
    ax.scatter([], [], s=110, color=AMBER, label="Trained model, no clear gain")
    ax.axvline(0.5, color=LINE, lw=1, ls="--")
    ax.set_xlim(0.56, 0.98)
    ax.set_yticks(range(len(seeds)), [f"simulated city {i + 1}" for i in range(len(seeds))], fontsize=11)
    ax.set_xlabel(f"Ranking quality (AUC, higher is better)\nmean {M['risk']['auc_formula_mean']:.2f} to {M['risk']['auc_best_model_mean']:.2f}; clearly better in {M['risk']['cities_where_model_wins_by_0.01']} of 10 cities", fontsize=12.5)
    ax.set_title("Hotspot risk: a trained model vs the formula", loc="left", fontsize=15, fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=10, loc="center right")

    ax2 = fig.add_axes([0.62, 0.27, 0.32, 0.5])
    d = M["duplicates"]
    names = ["Word overlap", "Sentence\nembeddings"]
    auc = [d["auc_word_overlap"], d["auc_embeddings"]]
    bars = ax2.bar(names, auc, color=[SLATE, ORANGE], width=0.5)
    for b, v in zip(bars, auc):
        ax2.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", fontsize=18, fontweight="bold")
    ax2.axhline(0.5, color=RED, lw=1.4, ls="--")
    ax2.text(1.42, 0.515, "coin flip", color=RED, ha="right", fontsize=11)
    ax2.set_ylim(0, 1.05)
    ax2.set_ylabel("AUC")
    ax2.set_title("Spotting a repeat report", loc="left", fontsize=15, fontweight="bold")
    ax2.spines[["top", "right"]].set_visible(False)
    ax2.text(0.5, -0.24, f"recall {d['embeddings_at_0.50']['recall']:.0%}, precision {d['embeddings_at_0.50']['precision']:.0%} on 40 hand-written pairs", transform=ax2.transAxes, ha="center", fontsize=11, color=MUTED)
    footer(
        fig,
        "Source: docs/ml_report/metrics.json. Risk: 10 simulated cities of 1,500 reports each, trained on the oldest 70% and scored on the newest 30%; a model is only deployed if it beats the formula by 0.01. "
        "Duplicates: 20 same-issue and 20 different-issue pairs written by hand, including 5 hard cases. Photo analysis (Gemini) has not been measured: there are no labelled photos yet.",
    )
    save(fig, "07_scorecard.png")


# ------------------------------------------------------------------------------------------ 8. roadmap/validation
def next_steps():
    fig = canvas("From simulated to proven", "What a pilot would measure, and how we would know it worked")
    ax = blank_axes(fig)
    cols = [
        ("Today", SLATE, ["Working product, 4 roles,\nmany cities", "Models tested on simulated\nand hand-written data", "75 automated tests"]),
        ("Pilot, 8 weeks", ORANGE, ["Real reports from one ward", "Hand-label 300 photos to\nmeasure the AI honestly", "Time to clear and\nrepeat-site rate"]),
        ("Proof", TEAL, ["Retrain risk on real history,\nship only if it wins", "Road-distance routes\nand real fuel logs", "Image check for the\nafter-photo"]),
    ]
    for i, (head, col, items) in enumerate(cols):
        x = 0.05 + i * 0.318
        box(ax, x, 0.7, 0.28, 0.075, head, fc=col, ec=col, tc="white", fs=17, bold=True)
        for j, t in enumerate(items):
            box(ax, x, 0.55 - j * 0.155, 0.28, 0.125, t, fc="white", ec=col, fs=13, lw=1.8)
        if i < 2:
            arrow(ax, (x + 0.283, 0.737), (x + 0.315, 0.737), color=INK, lw=2.2)
    footer(fig, "Targets are proposals for a pilot, not results. The 8-week length and 300-photo sample are our suggestion and are not yet agreed with any city.")
    save(fig, "08_next_steps.png")


if __name__ == "__main__":
    problem()
    loop()
    lifecycle()
    architecture()
    tenancy()
    routes()
    scorecard()
    next_steps()
