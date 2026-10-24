"""Live progress page for the two Android release builds.

    python scripts/apk_monitor/server.py            # then open http://localhost:8799

It reads the Gradle logs the builds write, works out which stage each build is in, and serves a JARVIS-style page
(index.html) that refreshes every 2 seconds. When an APK is finished the page offers it for download, so you can open
http://<this-computer>:8799 on a phone on the same Wi-Fi and install it from there.

Only the Python standard library is needed. It serves the two APK files and the page, nothing else.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(os.getenv("MONITOR_PORT", "8799"))
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TEMP = Path(os.getenv("TEMP", "/tmp"))
# Windows cannot build the native code from a deep folder (its 260-character path limit), so builds can run from a short copy of mobile/ such as C:\m
MOBILE = Path(os.getenv("MOBILE_BUILD_DIR", "C:/m" if Path("C:/m/apps").exists() else str(ROOT / "mobile")))

APPS = {
    "crew": {
        "title": "CIVICLOOP CREW",
        "log": Path(os.getenv("CREW_LOG", TEMP / "crew_build.log")),
        "apk_dir": MOBILE / "apps" / "crew" / "android" / "app" / "build" / "outputs" / "apk" / "release",
    },
    "resident": {
        "title": "CIVICLOOP RESIDENT",
        "log": Path(os.getenv("RESIDENT_LOG", TEMP / "resident_build.log")),
        "apk_dir": MOBILE / "apps" / "resident" / "android" / "app" / "build" / "outputs" / "apk" / "release",
    },
}

# (key, label, a task-name pattern that shows the stage has begun, share of the whole build)
STAGES = [
    ("setup", "Preparing the build", r".", 4),
    ("libs", "Compiling libraries", r"compile\w*(Java|Kotlin)", 20),
    ("bundle", "Bundling the app's JavaScript", r":app:createBundle\w*JsAndAssets", 12),
    ("native", "Compiling native code", r"buildCMake\w*\[", 36),
    ("package", "Packaging and optimising", r":app:(merge\w*Resources|dexBuilder|mergeDex|minify\w*R8|package\w*Release|lintVital)", 22),
    ("apk", "Signing the APK", r":app:(validateSigning|assembleRelease|createReleaseApkListingFileRedirect)", 6),
]

# ---------------------------------------------------------------------------------------------- GitHub Actions
# When a recent run of the workflow exists, the page follows that run (through the `gh` command) instead of the local logs.
WORKFLOW = "android-apks.yml"
DOWNLOADS = TEMP / "civicloop-apks"
STEP_WEIGHT = {"Accept the Android SDK licences (the SDK itself is already on the machine)": 1, "Install the JavaScript packages": 3, "Generate the native Android project": 2, "Build the release APK": 16}
STEP_EXPECTED_SECONDS = {"Build the release APK": 600, "Install the JavaScript packages": 90, "Generate the native Android project": 60}
HIDDEN_STEPS = ("Set up job", "Complete job")
_cache: dict = {"at": 0.0, "run": None}
_fetching: set[str] = set()


def gh_json(*args: str):
    try:
        done = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=30)
        return json.loads(done.stdout) if done.returncode == 0 and done.stdout.strip() else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def stamp(value: str | None) -> float | None:
    if not value or value.startswith("0001"):
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()


def github_run():
    """The newest run of the workflow if it is running now or started in the last three hours, else None."""
    now = time.time()
    if now - _cache["at"] < 4:
        return _cache["run"]
    run = None
    runs = gh_json("run", "list", "--workflow", WORKFLOW, "--limit", "1", "--json", "databaseId,status,createdAt")
    if runs:
        newest = runs[0]
        started = stamp(newest["createdAt"]) or 0
        if newest["status"] != "completed" or now - started < 3 * 3600:
            run = gh_json("run", "view", str(newest["databaseId"]), "--json", "databaseId,status,conclusion,url,jobs")
    _cache.update(at=now, run=run)
    return run


def fetch_apks(run_id: int) -> None:
    key = str(run_id)
    if key in _fetching:
        return
    _fetching.add(key)

    def work() -> None:
        subprocess.run(["gh", "run", "download", key, "-D", str(DOWNLOADS / key)], capture_output=True, timeout=600)

    threading.Thread(target=work, daemon=True).start()


def downloaded_apk(name: str):
    if not DOWNLOADS.exists():
        return None
    found = sorted(DOWNLOADS.glob(f"*/civicloop-{name}-release-apk/*.apk"), key=lambda p: p.stat().st_mtime)
    return found[-1] if found else None


def analyse_github(name: str, run: dict) -> dict:
    app = APPS[name]
    result: dict = {"name": name, "title": app["title"], "state": "waiting", "percent": 0, "stage": "Queued on GitHub", "stages": [], "tasks": 0, "elapsed": 0, "idle": 0, "feed": [], "apk": None, "error": None, "note": "", "link": run["url"]}
    job = next((j for j in run.get("jobs", []) if j["name"].lower().startswith(name)), None)
    if job is None:
        return result
    now = time.time()
    steps = [s for s in job.get("steps", []) if s["name"] not in HIDDEN_STEPS and not s["name"].startswith("Post ")]
    total = sum(STEP_WEIGHT.get(s["name"], 1) for s in steps) or 1
    gained, stages, feed, current = 0.0, [], [], None
    for step in steps:
        weight = STEP_WEIGHT.get(step["name"], 1)
        began, ended = stamp(step.get("startedAt")), stamp(step.get("completedAt"))
        if step["status"] == "completed":
            if step.get("conclusion") == "skipped":  # skipped because an earlier step failed
                stages.append({"label": step["name"], "state": "todo"})
                continue
            ok = step.get("conclusion") == "success"
            gained += weight if ok else 0
            stages.append({"label": step["name"], "state": "done" if ok else "failed"})
            seconds = int((ended or now) - (began or now))
            feed.append(f"> {'OK  ' if ok else 'FAIL'} {step['name']} ({seconds}s)")
        elif step["status"] == "in_progress":
            expected = STEP_EXPECTED_SECONDS.get(step["name"], 45)
            fraction = min(0.95, max(0.0, (now - (began or now)) / expected))
            gained += weight * fraction
            current = step["name"]
            stages.append({"label": step["name"], "state": "active"})
            feed.append(f"> RUN  {step['name']} ...")
        else:
            stages.append({"label": step["name"], "state": "todo"})
    started = stamp(job.get("startedAt"))
    finished = stamp(job.get("completedAt"))
    result.update(stages=stages, feed=feed[-9:], tasks=sum(1 for s in stages if s["state"] == "done"), percent=round(100 * gained / total))
    result["elapsed"] = int(((finished or now) - started)) if started else 0
    if job["status"] == "queued":
        result.update(state="waiting", stage="Waiting for a GitHub machine", percent=0)
    elif job["status"] == "in_progress":
        result.update(state="running", stage=current or "Working", percent=min(result["percent"], 97))
    elif job.get("conclusion") == "success":
        result.update(state="done", percent=100, stage="Build complete")
        local = downloaded_apk(name)
        if local:
            result["apk"] = {"file": local.name, "mb": round(local.stat().st_size / 1e6, 1), "url": f"/apk/{name}"}
        else:
            fetch_apks(run["databaseId"])
            result["note"] = "Fetching the APK from GitHub to this computer..."
    else:
        bad = next((s["name"] for s in steps if s.get("conclusion") == "failure"), "a step")
        result.update(state="failed", stage="Build failed", error=f"The step \"{bad}\" failed. Open the run on GitHub for the full log: {run['url']}")
    return result


TASK = re.compile(r"^> Task (\S+)(?: (\S.*))?$")


def read_tail(path: Path, limit: int = 600_000) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def analyse(name: str) -> dict:
    app = APPS[name]
    log: Path = app["log"]
    apk_dir: Path = app["apk_dir"]
    result: dict = {"name": name, "title": app["title"], "state": "waiting", "percent": 0, "stage": "Waiting to start", "stages": [], "tasks": 0, "elapsed": 0, "idle": 0, "feed": [], "apk": None, "error": None, "note": ""}

    apk = next(iter(sorted(apk_dir.glob("*.apk"))), None) if apk_dir.exists() else None
    if not log.exists():
        if apk:
            result.update(state="done", percent=100, stage="Finished", apk={"file": apk.name, "mb": round(apk.stat().st_size / 1e6, 1), "url": f"/apk/{name}"})
        return result

    text = read_tail(log)
    lines = text.splitlines()
    tasks = [m.group(1) for m in (TASK.match(line) for line in lines) if m]
    all_tasks = sum(1 for line in text.splitlines() if line.startswith("> Task"))
    stat = log.stat()
    now = time.time()
    result["tasks"] = max(all_tasks, len(tasks))
    result["idle"] = int(now - stat.st_mtime)
    # a build's folder is created when Gradle starts, so its creation time is when this build began
    build_dir = apk_dir.parents[2]
    began = build_dir.stat().st_ctime if build_dir.exists() else None
    result["elapsed"] = int(max(0, ((stat.st_mtime if "BUILD" in text else now) - began))) if began else 0
    result["feed"] = [line[:110] for line in lines if line.startswith("> Task")][-9:]

    succeeded = "BUILD SUCCESSFUL" in text
    failed = "BUILD FAILED" in text

    # stages reached, judged by the task names seen so far
    reached = 0
    joined = "\n".join(tasks)
    for index, (_, _, pattern, _) in enumerate(STAGES):
        if re.search(pattern, joined):
            reached = index
    done_weight = sum(stage[3] for stage in STAGES[:reached])
    here = STAGES[reached]
    percent = done_weight + here[3] * 0.5
    stage_label = here[1]
    if not tasks and not (succeeded or failed):
        percent, stage_label = 1, "Starting Gradle"
    result["stages"] = [{"label": label, "state": "done" if i < reached else ("active" if i == reached else "todo")} for i, (_, label, _, _) in enumerate(STAGES)]

    if succeeded:
        result.update(state="done", percent=100, stage="Build complete")
        result["stages"] = [{"label": label, "state": "done"} for _, label, _, _ in STAGES]
        if apk:
            result["apk"] = {"file": apk.name, "mb": round(apk.stat().st_size / 1e6, 1), "url": f"/apk/{name}"}
    elif failed:
        match = re.search(r"\* What went wrong:\n(.+?)(?:\n\*|\Z)", text, re.S)
        reason = " ".join((match.group(1) if match else "The build failed").split())[:320]
        result.update(state="failed", percent=round(percent), stage="Build failed", error=reason)
    else:
        result.update(state="running", percent=round(min(percent, 97)), stage=stage_label)
        if result["idle"] > 75:
            result["note"] = f"Quiet for {result['idle']} s. Usually Gradle is downloading libraries or compiling native code."
    return result


def lan_address() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def send(self, status: int, body: bytes, kind: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/status":
            run = github_run()
            apps = [analyse_github(name, run) for name in APPS] if run else [analyse(name) for name in APPS]
            payload = {"time": int(time.time()), "host": f"http://{lan_address()}:{PORT}", "source": f"GITHUB ACTIONS  {run['url']}" if run else "LOCAL BUILD LOGS", "apps": apps}
            self.send(200, json.dumps(payload).encode(), "application/json")
        elif path.startswith("/apk/") and path[5:] in APPS:
            name = path[5:]
            folder: Path = APPS[name]["apk_dir"]
            apk = downloaded_apk(name) or (next(iter(sorted(folder.glob("*.apk"))), None) if folder.exists() else None)
            if not apk:
                self.send(404, b"APK not built yet", "text/plain")
                return
            self.send(200, apk.read_bytes(), "application/vnd.android.package-archive", {"Content-Disposition": f'attachment; filename="civicloop-{name}.apk"'})
        else:
            self.send(404, b"Not found", "text/plain")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"APK build monitor: http://localhost:{PORT}   (on your Wi-Fi: http://{lan_address()}:{PORT})")
    server.serve_forever()
