"""Lay every screenshot of one app side by side on a single image, each in a simple phone outline.

Run: python mobile/scripts/contact_sheet.py docs/mobile
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/mobile")
TITLES = {
    "resident": "CivicLoop (residents)",
    "crew": "CivicLoop Crew",
}
LABELS = {
    "00-welcome-1": "Welcome 1",
    "00-welcome-2": "Welcome 2",
    "00-welcome-3": "Welcome 3",
    "11-route": "Your route",
    "01-sign-in": "Sign in",
    "02-create-account": "Create account",
    "03-server-address": "Server address",
    "04-my-reports": "My reports",
    "05-report-empty": "Report waste",
    "06-report-filled": "Filled in",
    "07-report-detail": "Report detail",
    "08-account": "Account",
    "02-jobs-todo": "My jobs",
    "03-jobs-done": "Done jobs",
    "04-job-detail": "Job detail",
    "05-location": "Vehicle location",
    "06-location-sharing": "Sharing",
    "07-report": "Report a site",
    "09-sign-out-dialog": "Sign-out dialog",
    "10-location-explainer": "Location explainer",
    "12-pull-to-refresh": "Pull to refresh",
    "13-not-found": "Not found screen",
    "09-confirm-done-dialog": "Confirm dialog",
    "10-share-explainer": "Sharing explainer",
}
WIDTH, GAP, PAD, ROW_H = 300, 28, 40, 700
INK, BG, ACCENT = (20, 33, 61), (244, 246, 251), (212, 80, 26)


def font(size: int, bold: bool = False):
    for name in ("arialbd.ttf" if bold else "arial.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def sheet(app: str) -> None:
    files = sorted((ROOT / app).glob("[0-9][0-9]-*.png"))
    if not files:
        return
    per_row = 4
    rows = [files[i : i + per_row] for i in range(0, len(files), per_row)]
    width = PAD * 2 + per_row * WIDTH + (per_row - 1) * GAP
    height = 120 + len(rows) * (ROW_H + 70) + PAD
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((PAD, 36), TITLES[app], fill=ACCENT, font=font(40, True))
    draw.text((PAD, 86), "Real app screens, rendered at phone size", fill=(91, 100, 120), font=font(20))
    y = 130
    for row in rows:
        for i, file in enumerate(row):
            shot = Image.open(file).convert("RGB")
            scale = WIDTH / shot.width
            shot = shot.resize((WIDTH, int(shot.height * scale)), Image.LANCZOS)
            visible = shot.crop((0, 0, WIDTH, min(shot.height, ROW_H)))  # tall forms show their top part
            x = PAD + i * (WIDTH + GAP)
            draw.rounded_rectangle([x - 8, y - 8, x + WIDTH + 8, y + visible.height + 8], radius=26, fill=INK)
            mask = Image.new("L", visible.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, visible.width, visible.height], radius=20, fill=255)
            canvas.paste(visible, (x, y), mask)
            label = LABELS.get(file.stem, file.stem)
            draw.text((x, y + visible.height + 18), label, fill=INK, font=font(22, True))
        y += ROW_H + 70
    out = ROOT / f"{app}-overview.png"
    canvas.save(out)
    print("wrote", out)


if __name__ == "__main__":
    for app in TITLES:
        sheet(app)
