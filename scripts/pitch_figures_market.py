"""Market slides for CivicLoopAI: feasibility ranking and pricing. Run: python scripts/pitch_figures_market.py

Scores are our own judgement (see docs/pitch/market-and-pricing.md). The pricing example is an estimate built on
stated assumptions, not a measured result. Uses the helpers and palette from pitch_figures.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt  # noqa: E402

from pitch_figures import (  # noqa: E402
    AMBER,
    BLUE,
    INK,
    MUTED,
    ORANGE,
    SLATE,
    TEAL,
    blank_axes,
    box,
    canvas,
    footer,
    save,
)

# Chandigarh-size example. Every input is stated in the footer of the slide.
TONNES_PER_DAY = 540  # CPCB 2021-22
RS_PER_TONNE = (500, 1000)  # older ULB benchmark
INFLUENCED_SHARE = 0.5  # assumption: routing can influence half of spend
SAVING = 0.05  # assumption, inside the 4.8 to 8% other cities report
VEHICLES = 270  # Tribune report on Chandigarh's collection fleet
PLATFORM_LAKH, PER_VEHICLE_MONTH = 1.0, 250


def example():
    spend = [TONNES_PER_DAY * 365 * r / 1e7 for r in RS_PER_TONNE]  # crore
    saving = [s * INFLUENCED_SHARE * SAVING * 100 for s in spend]  # lakh
    price = max(2.0, PLATFORM_LAKH + VEHICLES * PER_VEHICLE_MONTH * 12 / 1e5)  # lakh
    return spend, saving, price


def feasibility():
    fig = canvas("Where to sell first", "Our assessment of each route to revenue over the next 12 months, scored 1 to 10")
    rows = [
        ("City pilot, no fee\n(MoU with one city)", 8.0, "G", "Easy to start; earns credibility, not revenue"),
        ("Waste contractors\n(fleet operators)", 6.5, "B", "Pay for proof of service and fewer wasted trips"),
        ("Bulk-generator compliance\n(malls, campuses, hospitals)", 6.0, "B", "New 2026 rules create demand; features not built yet"),
        ("Paid city licence\n(direct purchase)", 4.5, "G", "Small tickets, slow payment, tight city budgets"),
        ("State tender or\nsmart-city integrator", 3.0, "G", "Big tenders are GPS hardware; lowest bid wins"),
        ("Citizens pay\n(consumer app)", 1.5, "C", "A free government app already covers reporting"),
    ]
    colour = {"G": BLUE, "B": ORANGE, "C": SLATE}
    ax = fig.add_axes([0.27, 0.19, 0.68, 0.6])
    for i, (name, score, kind, why) in enumerate(rows[::-1]):
        ax.barh(i, score, color=colour[kind], height=0.62, zorder=2)
        ax.text(score + 0.15, i + 0.1, f"{score:.1f}", va="center", fontsize=17, fontweight="bold")
        ax.text(0.15, i - 0.47, why, va="center", fontsize=11.2, color=MUTED)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows[::-1]], fontsize=13)
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.75, len(rows) - 0.35)
    ax.set_xticks([])
    ax.spines[["top", "right", "bottom"]].set_visible(False)
    ax.tick_params(left=False)
    for x, label, c in ((0.27, "Business to government", BLUE), (0.5, "Business to business", ORANGE), (0.7, "Consumer", SLATE)):
        fig.patches.append(plt.Rectangle((x, 0.115), 0.012, 0.022, transform=fig.transFigure, fc=c, ec=c))
        fig.text(x + 0.018, 0.126, label, fontsize=12, va="center")
    footer(
        fig,
        "Scores are our judgement from the research in docs/pitch/market-and-pricing.md, not a measurement. They weigh how easy the buyer is to reach, how fast and how reliably they pay, "
        "how well the product fits today, and the size of the ticket.",
    )
    save(fig, "09_feasibility.png")


def pricing():
    spend, saving, price = example()
    fig = canvas("Priced against what it saves", "Annual subscription, billed once a year. Example: a city the size of Chandigarh, 270 collection vehicles")
    ax = blank_axes(fig)
    tiers = [
        ("City pilot", "Rs 0", "90 days, 1 to 2 wards, up to 25\nvehicles. Credited to year one\nif the city continues.", SLATE),
        ("City licence", "Rs 1 lakh + Rs 250 a vehicle a month", "Minimum Rs 2 lakh a year.\n270 vehicles = Rs 9.1 lakh.\nAll roles, AI and routes included.", BLUE),
        ("Contractor", "Rs 400 a vehicle a month", "Minimum 25 vehicles. Proof-of-\nservice photos, routes, and\nreports for the paying city.", ORANGE),
        ("Bulk generator", "Rs 12,000 to 30,000 a site a year", "Registration reminders, segre-\ngation logs, audit-ready\nrecords, vendor photo proof.", TEAL),
    ]
    for i, (name, cost, note, col) in enumerate(tiers):
        x = 0.05 + i * 0.2325
        w = 0.215
        box(ax, x, 0.5, w, 0.28, "", fc="white", ec=col, lw=2.4, r=0.012)
        box(ax, x, 0.7, w, 0.08, name, fc=col, ec=col, tc="white", fs=14, bold=True, r=0.012)
        ax.text(x + w / 2, 0.655, cost, ha="center", va="center", fontsize=9.6, fontweight="bold")
        ax.text(x + w / 2, 0.565, note, ha="center", va="center", fontsize=10, color=MUTED, linespacing=1.3)

    axv = fig.add_axes([0.2, 0.2, 0.74, 0.2])
    lo, hi = saving
    axv.barh(1, hi - lo, left=lo, color="#cfe9e1", height=0.5, zorder=2)
    axv.barh(1, 0.6, left=lo, color=TEAL, height=0.5, zorder=3)
    axv.barh(1, 0.6, left=hi - 0.6, color=TEAL, height=0.5, zorder=3)
    axv.text((lo + hi) / 2, 1.0, f"Rs {lo:.0f} to {hi:.0f} lakh", ha="center", va="center", fontsize=14, fontweight="bold", color="#145b49")
    axv.barh(0, price, color=BLUE, height=0.5, zorder=2)
    axv.text(price + 1, 0, f"Rs {price:.1f} lakh", va="center", fontsize=14, fontweight="bold", color=BLUE)
    axv.set_yticks([0, 1], ["Price", "Estimated\nyearly saving"], fontsize=13)
    axv.set_xlim(0, 56)
    axv.set_ylim(-0.5, 1.6)
    axv.set_xlabel("Rs lakh a year", fontsize=11.5)
    axv.spines[["top", "right"]].set_visible(False)
    breakeven_lo = price / (spend[1] * INFLUENCED_SHARE * 100) * 100
    breakeven_hi = price / (spend[0] * INFLUENCED_SHARE * 100) * 100
    axv.set_title(f"Chandigarh-size city: it pays for itself at a {breakeven_lo:.0f} to {breakeven_hi:.0f}% saving", loc="left", fontsize=14, fontweight="bold")
    footer(
        fig,
        f"Estimate, not a result. {TONNES_PER_DAY} t a day x 365 x Rs {RS_PER_TONNE[0]} to {RS_PER_TONNE[1]:,} a tonne (older benchmark) = Rs {spend[0]:.1f} to {spend[1]:.1f} crore a year; we assume routing can influence half of that "
        f"and save {SAVING:.0%}, inside the 4.8 to 8% other cities report. {VEHICLES} vehicles is from a Tribune report on Chandigarh's collection fleet. Per-vehicle platform fees of Rs 75 to 400 a month "
        "are vendor-blog figures, not tender prices. Check every number against the city's own accounts.",
    )
    save(fig, "10_pricing.png")


def competitors():
    fig = canvas("Who else is in this space", "From public descriptions. Hollow means we found nothing public, not that it is absent.")
    cols = ["Government\ncomplaint apps", "City waste-ops\nplatforms", "Compliance and\nmarketplace", "Global route and\nsensor software", "CivicLoop"]
    rows = [
        ("Citizen reporting with photo", ["F", "H", "N", "N", "F"]),
        ("Live vehicle tracking (GPS, RFID)", ["N", "F", "N", "F", "N"]),
        ("Route optimisation", ["N", "F", "N", "F", "F"]),
        ("AI reads the photo", ["N", "N", "N", "H", "F"]),
        ("Closure needs an after-photo", ["H", "H", "H", "H", "F"]),
        ("Predicts repeat hotspots", ["N", "N", "N", "H", "H"]),
        ("Bulk-generator compliance", ["H", "N", "F", "N", "N"]),
        ("Many cities, data kept apart", ["F", "F", "F", "F", "F"]),
        ("Priced for a small Indian city", ["F", "H", "N", "N", "F"]),
    ]
    symbol = {"F": "●", "H": "◐", "N": "○"}
    colour = {"F": TEAL, "H": AMBER, "N": "#b9c0d0"}
    ax = fig.add_axes([0.05, 0.24, 0.9, 0.56])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(rows) + 1.2)
    ax.axis("off")
    left = 0.30
    cw = (1 - left) / len(cols)
    ax.add_patch(plt.Rectangle((left + 4 * cw, 0), cw, len(rows) + 1.2, fc="#fff1e8", ec="none", zorder=0))
    for j, c in enumerate(cols):
        ax.text(left + (j + 0.5) * cw, len(rows) + 0.55, c, ha="center", va="center", fontsize=12, fontweight="bold", color=(ORANGE if j == 4 else INK), linespacing=1.15)
    for i, (label, vals) in enumerate(rows):
        y = len(rows) - i - 0.5
        ax.text(0.0, y, label, va="center", fontsize=12.5)
        ax.plot([0, 1], [y - 0.5, y - 0.5], color="#e6e9f2", lw=1)
        for j, v in enumerate(vals):
            ax.text(left + (j + 0.5) * cw, y, symbol[v], ha="center", va="center", fontsize=22, color=colour[v])
    fig.text(0.05, 0.195, "●  does it, publicly      ◐  partly, or only claimed by the vendor      ○  nothing public found", fontsize=11.5, color=MUTED)
    footer(
        fig,
        "Category-level, from public descriptions and vendor marketing, none independently tested. Government: Swachhata-MoHUA, Indore 311, MCD 311, PMC CARE, Bengaluru Anveshak. "
        "City platforms: WeVOIS, SafaiMitra, Convexicon, NEC. Compliance: Recykal. Global: Routeware, Rubicon, Enevo, Sensoneo. Our column is from our own code; its AI and risk model "
        "are unproven on real data. See docs/pitch/competitors.md.",
    )
    save(fig, "11_competitors.png")


if __name__ == "__main__":
    feasibility()
    pricing()
    competitors()
