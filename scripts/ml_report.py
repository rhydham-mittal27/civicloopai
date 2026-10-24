"""Regenerates the ML evaluation report: figures and numbers for the three ML components.

    python scripts/ml_report.py            # writes docs/ml_report/*.png and metrics.json

What it measures, and what it cannot:
- Risk model: validated on SYNTHETIC history only (no real reports exist yet). Repeated over 10
  random synthetic cities to show how stable the gain over the hand-set formula is.
- Routing: random stop layouts, OR-Tools vs nearest-neighbour. Pure optimisation, no data needed.
- Duplicates: a small hand-written set of description pairs. Indicative only.
- Photo analysis (Gemini): not measured. It needs labelled photos, which do not exist yet.
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score, roc_curve  # noqa: E402
from sqlalchemy import select  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("CIVICLOOP_MODEL_DIR", tempfile.mkdtemp(prefix="civicloop-report-"))

from civicloop.db import create_engine, create_session_factory, init_db  # noqa: E402
from civicloop.embeddings import FastEmbedder, text_similarity  # noqa: E402
from civicloop.engines.common import jaccard_text  # noqa: E402
from civicloop.engines.routing import RouteEngine, RouteEngineConfig  # noqa: E402
from civicloop.models import AnalysisResult, Incident, User  # noqa: E402
from civicloop.risk_model import (  # noqa: E402
    FEATURES,
    TrainingRow,
    baseline_formula,
    build_dataset,
    make_candidate,
)
from civicloop.synthetic import SYNTHETIC_EMAIL, seed_synthetic_history  # noqa: E402

OUT = ROOT / "docs" / "ml_report"
OUT.mkdir(parents=True, exist_ok=True)
INK, ACCENT, GREY, BLUE, GREEN = "#14213d", "#b83a00", "#8d99ae", "#2563eb", "#1b7f4c"
plt.rcParams.update(
    {
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#555",
        "axes.titleweight": "bold",
        "axes.titlesize": 11,
        "figure.dpi": 130,
        "savefig.bbox": "tight",
    }
)
metrics: dict = {}


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", name)


# ============================================================ 1. risk model
def synthetic_rows(seed: int):
    path = os.path.join(tempfile.gettempdir(), f"civicloop_report_{seed}.db")
    if os.path.exists(path):
        os.remove(path)
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    with create_session_factory(engine)() as session:
        seed_synthetic_history(session, 1500, seed=seed)
        latest = {a.incident_id: a for a in session.scalars(select(AnalysisResult))}
        synth = set(session.scalars(select(User.id).where(User.email == SYNTHETIC_EMAIL)))
        rows = [
            TrainingRow(i.id, i.latitude, i.longitude, i.occurred_at, latest[i.id].severity, latest[i.id].confidence, i.reporter_id in synth)
            for i in session.scalars(select(Incident))
        ]
    engine.dispose()
    return rows


def split(rows, now):
    data = build_dataset(rows, now)
    cut = int(len(data["y"]) * 0.7)
    return data["X"][:cut], data["X"][cut:], data["y"][:cut], data["y"][cut:]


now = datetime.now(timezone.utc)
per_seed = []
keep = None
for seed in range(10):
    Xtr, Xva, ytr, yva = split(synthetic_rows(seed), now)
    lr = make_candidate("logistic_regression").fit(Xtr, ytr)
    gb = make_candidate("gradient_boosting").fit(Xtr, ytr)
    row = {
        "seed": seed,
        "positive_rate": float(np.concatenate([ytr, yva]).mean()),
        "formula": roc_auc_score(yva, baseline_formula(Xva)),
        "logistic": roc_auc_score(yva, lr.predict_proba(Xva)[:, 1]),
        "gbm": roc_auc_score(yva, gb.predict_proba(Xva)[:, 1]),
    }
    per_seed.append(row)
    if seed == 7:
        keep = (lr, gb, Xtr, Xva, ytr, yva)
    print("risk seed", seed, {k: round(v, 3) for k, v in row.items()})

lr, gb, Xtr, Xva, ytr, yva = keep
formula_va = baseline_formula(Xva)
best = np.array([max(r["logistic"], r["gbm"]) for r in per_seed])
form = np.array([r["formula"] for r in per_seed])
metrics["risk"] = {
    "data": "synthetic, 1,500 reports per city, 10 random cities",
    "validation": "chronological, oldest 70% train / newest 30% test",
    "per_seed": per_seed,
    "auc_formula_mean": float(form.mean()),
    "auc_formula_sd": float(form.std()),
    "auc_best_model_mean": float(best.mean()),
    "auc_best_model_sd": float(best.std()),
    "gain_mean": float((best - form).mean()),
    "gain_min": float((best - form).min()),
    "gain_max": float((best - form).max()),
    "cities_where_model_wins_by_0.01": int(((best - form) >= 0.01).sum()),
}

# ROC
fig, ax = plt.subplots(figsize=(5.2, 4.6))
for name, score, colour, style in [
    ("Hand-set formula", formula_va, GREY, "--"),
    ("Gradient boosting", gb.predict_proba(Xva)[:, 1], BLUE, "-"),
    ("Logistic regression", lr.predict_proba(Xva)[:, 1], ACCENT, "-"),
]:
    fpr, tpr, _ = roc_curve(yva, score)
    ax.plot(fpr, tpr, style, color=colour, lw=2, label=f"{name} (AUC {roc_auc_score(yva, score):.3f})")
ax.plot([0, 1], [0, 1], ":", color="#bbb")
ax.set(xlabel="False positive rate", ylabel="True positive rate", title="Risk model on unseen reports (synthetic city, seed 7)")
ax.legend(loc="lower right", frameon=False)
save(fig, "fig_risk_roc.png")

# calibration
p = lr.predict_proba(Xva)[:, 1]
frac, mean_p = calibration_curve(yva, p, n_bins=8, strategy="quantile")
fig, ax = plt.subplots(figsize=(5.2, 4.6))
ax.plot([0, 1], [0, 1], ":", color="#bbb", label="Perfect")
ax.plot(mean_p, frac, "o-", color=ACCENT, lw=2, label="Logistic regression")
ax.set(xlabel="Predicted chance of recurrence", ylabel="Share that actually recurred", title="Are the probabilities honest?", xlim=(0, 1), ylim=(0, 1))
ax.legend(frameon=False)
save(fig, "fig_risk_calibration.png")

# stability across cities
fig, ax = plt.subplots(figsize=(6.4, 4.2))
xs = np.arange(10)
ax.vlines(xs, form, best, color="#cfd4dc", lw=2)
ax.scatter(xs, form, color=GREY, s=48, label="Hand-set formula", zorder=3)
ax.scatter(xs, best, color=ACCENT, s=48, label="Best trained model", zorder=3)
ax.set(xticks=xs, xlabel="Random synthetic city", ylabel="AUC on unseen reports", title="Gain over the formula, across 10 simulated cities")
ax.legend(frameon=False, loc="lower right")
save(fig, "fig_risk_stability.png")

# importance
imp = permutation_importance(lr, Xva, yva, scoring="roc_auc", n_repeats=8, random_state=7)
order = np.argsort(imp.importances_mean)
fig, ax = plt.subplots(figsize=(6, 3.8))
ax.barh([FEATURES[i] for i in order], imp.importances_mean[order], xerr=imp.importances_std[order], color=ACCENT, ecolor="#999")
ax.set(xlabel="AUC lost when the input is shuffled", title="What the risk model relies on")
save(fig, "fig_risk_importance.png")
metrics["risk"]["importance"] = {FEATURES[i]: float(imp.importances_mean[i]) for i in order[::-1]}

# ============================================================ 2. routing
def instance(n, seed):
    rng = random.Random(seed)
    from types import SimpleNamespace as NS

    inc = {str(i): NS(latitude=30.68 + rng.random() * 0.08, longitude=76.72 + rng.random() * 0.08) for i in range(n)}
    orders = [NS(id=f"o{i}", incident_id=str(i), priority=rng.choice([1, 5, 20, 50, 100]), estimated_volume=1.0) for i in range(n)]
    return orders, inc


depot = (30.72, 76.76)
routing = {}
for n in (10, 20, 30):
    res = {"pure": [], "priority": [], "ms": [], "urgent_rank_greedy": [], "urgent_rank_priority": []}
    for seed in range(12):
        orders, inc = instance(n, seed)
        g = RouteEngine(RouteEngineConfig(solver="greedy")).build(orders, inc, 1000, depot=depot)
        t = time.time()
        pure = RouteEngine(RouteEngineConfig(priority_weight=0, time_limit_seconds=2)).build(orders, inc, 1000, depot=depot)
        res["ms"].append((time.time() - t) * 1000)
        pr = RouteEngine(RouteEngineConfig(time_limit_seconds=2)).build(orders, inc, 1000, depot=depot)
        res["pure"].append(100 * (g.distance_km - pure.distance_km) / g.distance_km)
        res["priority"].append(100 * (g.distance_km - pr.distance_km) / g.distance_km)
        urgent = {o.id for o in orders if o.priority == 100}

        def mean_rank(result):
            ranks = [s.sequence / (n - 1) for s in result.stops if s.work_order_id in urgent]
            return float(np.mean(ranks)) if ranks else float("nan")

        res["urgent_rank_greedy"].append(mean_rank(g))
        res["urgent_rank_priority"].append(mean_rank(pr))
    routing[n] = res
    print("routing", n, {k: round(float(np.nanmean(v)), 2) for k, v in res.items()})
metrics["routing"] = {
    str(n): {
        "pure_saving_pct_mean": float(np.mean(r["pure"])),
        "priority_saving_pct_mean": float(np.mean(r["priority"])),
        "solve_ms_mean": float(np.mean(r["ms"])),
        "urgent_stop_position_greedy": float(np.nanmean(r["urgent_rank_greedy"])),
        "urgent_stop_position_priority": float(np.nanmean(r["urgent_rank_priority"])),
        "instances": 12,
    }
    for n, r in routing.items()
}

fig, ax = plt.subplots(figsize=(6.4, 4.2))
pos = np.arange(3)
b1 = ax.boxplot([routing[n]["pure"] for n in (10, 20, 30)], positions=pos - 0.18, widths=0.3, patch_artist=True, showfliers=False)
b2 = ax.boxplot([routing[n]["priority"] for n in (10, 20, 30)], positions=pos + 0.18, widths=0.3, patch_artist=True, showfliers=False)
for b, c in ((b1, BLUE), (b2, ACCENT)):
    for box in b["boxes"]:
        box.set(facecolor=c, alpha=0.75)
    for m in b["medians"]:
        m.set(color="white", lw=2)
ax.axhline(0, color="#999", lw=1)
ax.set(xticks=pos, xticklabels=["10 stops", "20 stops", "30 stops"], ylabel="% shorter than nearest-neighbour", title="OR-Tools vs nearest-neighbour (12 random layouts each)")
ax.legend([b1["boxes"][0], b2["boxes"][0]], ["Shortest tour", "With urgent-stop pull (default)"], frameon=False, loc="upper left")
save(fig, "fig_routes_savings.png")

orders, inc = instance(25, 4)
g = RouteEngine(RouteEngineConfig(solver="greedy")).build(orders, inc, 1000, depot=depot)
o = RouteEngine(RouteEngineConfig(time_limit_seconds=2)).build(orders, inc, 1000, depot=depot)
fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.4), sharex=True, sharey=True)
for ax, res, title, colour in ((axes[0], g, "Nearest-neighbour", GREY), (axes[1], o, "OR-Tools", ACCENT)):
    pts = [depot] + [(s.latitude, s.longitude) for s in res.stops] + [depot]
    ax.plot([p[1] for p in pts], [p[0] for p in pts], "-", color=colour, lw=1.6, alpha=0.9)
    prio = {x.id: x.priority for x in orders}
    for s in res.stops:
        ax.scatter(s.longitude, s.latitude, s=18 + prio[s.work_order_id] * 1.3, color=INK if prio[s.work_order_id] == 100 else "#6b7280", zorder=3)
    ax.scatter(depot[1], depot[0], marker="*", s=200, color=GREEN, zorder=4)
    ax.set_title(f"{title}: {res.distance_km:.1f} km")
    ax.set_xticks([])
    ax.set_yticks([])
fig.suptitle("Same 25 stops (dark = urgent, star = depot)", fontsize=10)
save(fig, "fig_route_map.png")

# ============================================================ 3. duplicates
POS = [
    ("Overflowing bins behind the market", "Garbage heaped up near the market stalls"),
    ("Construction rubble dumped on the footpath", "Bricks and debris left on the pavement"),
    ("Dead dog lying on the main road", "Carcass of a dog on the road"),
    ("Plastic bags and bottles scattered in the park", "Park littered with plastic bottles and bags"),
    ("Old sofa and mattress left outside the school", "Discarded furniture dumped by the school wall"),
    ("Burning garbage near the bus stop", "Someone set trash on fire at the bus stand"),
    ("Drain blocked and overflowing onto the lane", "Clogged drain, dirty water spilling over the street"),
    ("Food waste rotting behind the restaurant", "Rotten kitchen waste piled behind the eatery"),
    ("Medical waste dumped near the clinic", "Syringes and bandages thrown outside the clinic"),
    ("Garbage truck has not come for a week", "No waste collection here for seven days"),
    ("Pile of garbage at the corner of sector 17", "Trash heap on the sector 17 corner"),
    ("Leaves and branches blocking the pavement", "Tree cuttings dumped across the footpath"),
    ("Overflowing dustbin outside the temple", "Temple dustbin is full and spilling over"),
    ("Sewage leaking onto the road", "Sewer water flowing across the street"),
    ("Waste dumped in the empty plot", "Garbage thrown into the vacant plot"),
    ("Dumpster is overflowing in the parking lot", "Parking lot bin overflowing with trash"),
    ("Broken glass and litter near the metro exit", "Glass shards and rubbish by the metro exit"),
    ("Cardboard boxes and packaging left on the street", "Packaging waste and boxes dumped on the road"),
    ("Smelly garbage near the fish market", "Foul-smelling waste outside the fish market"),
    ("Bags of waste dumped along the canal", "Trash bags thrown beside the canal"),
]
NEG = [
    ("Overflowing bins behind the market", "Burnt-out streetlight on the main road"),
    ("Construction rubble dumped on the footpath", "Loud construction noise at night"),
    ("Dead dog lying on the main road", "Plastic bags scattered in the park"),
    ("Old sofa left outside the school", "Pothole on the school road"),
    ("Burning garbage near the bus stop", "Bus shelter roof is broken"),
    ("Drain blocked near the lane", "Stray dogs barking at night"),
    ("Food waste behind the restaurant", "Illegal parking outside the restaurant"),
    ("Medical waste near the clinic", "Clinic signboard is missing"),
    ("Garbage truck has not come for a week", "Water supply cut for two days"),
    ("Pile of garbage at the corner of sector 17", "Graffiti on the wall at sector 22"),
    ("Overflowing dustbin outside the temple", "Loudspeaker too loud at the temple"),
    ("Sewage leaking onto the road", "Fallen tree blocking the road"),
    ("Waste dumped in the empty plot", "Broken swing in the playground"),
    ("Dumpster overflowing in the parking lot", "Car abandoned in the parking lot"),
    ("Broken glass near the metro exit", "Escalator not working at the metro"),
    # hard negatives: same words, different problem
    ("Overflowing bins behind the market", "Overflowing drain behind the market"),
    ("Garbage dumped near the school", "Garbage dumped near the hospital"),
    ("Plastic waste in the park", "Fallen branches in the park"),
    ("Smelly garbage near the fish market", "Smelly open drain near the fish market"),
    ("Dead dog lying on the main road", "Dead tree lying across the main road"),
]
emb = FastEmbedder()
y = np.array([1] * len(POS) + [0] * len(NEG))
pairs = POS + NEG
jac = np.array([jaccard_text(a, b) for a, b in pairs])
sem = np.array([text_similarity(emb, a, b) for a, b in pairs])


def prf(score, thr):
    pred = score >= thr
    tp = int((pred & (y == 1)).sum())
    return {"precision": tp / max(int(pred.sum()), 1), "recall": tp / int(y.sum())}


# the thresholds each method would have to use in the duplicate score
metrics["duplicates"] = {
    "data": f"{len(POS)} same-issue and {len(NEG)} different-issue description pairs, written by hand (incl. 5 hard negatives)",
    "auc_word_overlap": float(roc_auc_score(y, jac)),
    "auc_embeddings": float(roc_auc_score(y, sem)),
    "word_overlap_at_0.30": prf(jac, 0.30),
    "embeddings_at_0.50": prf(sem, 0.50),
    "embedding_model": "BAAI/bge-small-en-v1.5 (quantised ONNX, no fine-tuning)",
}
fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9), sharey=True)
for ax, score, title, colour in ((axes[0], jac, f"Word overlap (AUC {roc_auc_score(y, jac):.2f})", GREY), (axes[1], sem, f"Sentence embeddings (AUC {roc_auc_score(y, sem):.2f})", ACCENT)):
    bins = np.linspace(0, 1, 11)
    ax.hist(score[y == 0], bins=bins, alpha=0.75, color="#9aa5b1", label="Different issue")
    ax.hist(score[y == 1], bins=bins, alpha=0.8, color=colour, label="Same issue")
    ax.set(title=title, xlabel="Text similarity (0-1)")
axes[0].set_ylabel("Pairs")
axes[1].legend(frameon=False)
save(fig, "fig_dup_scores.png")

# ============================================================ 4. architecture
fig, ax = plt.subplots(figsize=(11, 4.3))
ax.axis("off")
ax.set_xlim(0, 11)
ax.set_ylim(0, 4.3)


def box(x, y_, w, h, text, face, edge=INK, size=9, bold=False):
    ax.add_patch(plt.Rectangle((x, y_), w, h, facecolor=face, edgecolor=edge, lw=1.4, joinstyle="round"))
    ax.text(x + w / 2, y_ + h / 2, text, ha="center", va="center", fontsize=size, color=INK, fontweight="bold" if bold else "normal", wrap=True)


def arrow(x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#555", lw=1.3))


box(0.1, 1.7, 1.5, 0.9, "Report\nphoto + text + GPS", "#eef2f7")
box(2.1, 1.7, 1.8, 0.9, "Gemini 2.5 Flash\ncategory, severity,\nconfidence", "#fde8d9", ACCENT, bold=True)
box(4.4, 3.0, 2.2, 0.9, "Risk model\nlogistic regression / GBM\n(chance of recurrence)", "#fde8d9", ACCENT, bold=True)
box(4.4, 1.7, 2.2, 0.9, "Duplicate finder\nbge-small embeddings\n+ distance + time", "#fde8d9", ACCENT, bold=True)
box(4.4, 0.4, 2.2, 0.9, "Cleanup check\nrule: job done and\nphoto is new", "#eef2f7")
box(7.1, 1.7, 1.7, 0.9, "Supervisor\nreviews and\ndecides", "#dbeafe", BLUE, bold=True)
box(9.2, 2.4, 1.6, 0.9, "Route planner\nOR-Tools VRP", "#fde8d9", ACCENT, bold=True)
box(9.2, 0.9, 1.6, 0.9, "Worker cleans,\nsends photo", "#eef2f7")
arrow(1.6, 2.15, 2.1, 2.15)
arrow(3.9, 2.3, 4.4, 3.4)
arrow(3.9, 2.15, 4.4, 2.15)
arrow(6.6, 3.4, 7.3, 2.6)
arrow(6.6, 2.15, 7.1, 2.15)
arrow(8.8, 2.3, 9.2, 2.8)
arrow(10.0, 2.4, 10.0, 1.8)
arrow(9.2, 1.2, 6.6, 0.85)
arrow(5.5, 1.3, 5.5, 1.7)
ax.text(5.5, 4.15, "Orange = ML/AI. Blue = human decision. Grey = rules.", ha="center", fontsize=9, color="#555")
save(fig, "fig_architecture.png")

(OUT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
print("wrote metrics.json")
