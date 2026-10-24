// GitHub Pages edition: no local server, so the page asks the GitHub API for the newest build itself.
const REPO = "rhydham-mittal27/civicloopai";
const API = `https://api.github.com/repos/${REPO}`;
const TITLES = { crew: "CIVICLOOP CREW", resident: "CIVICLOOP RESIDENT" };
const WEIGHT = { "Install the JavaScript packages": 3, "Generate the native Android project": 2, "Build the release APK": 16 };
const EXPECTED = { "Build the release APK": 600, "Install the JavaScript packages": 90, "Generate the native Android project": 60 };
let limited = false;

const secs = (v) => (v && !v.startsWith("0001") ? Date.parse(v) / 1000 : null);

async function gh(path) {
  const response = await fetch(`${API}${path}`, { headers: { Accept: "application/vnd.github+json" } });
  if (response.status === 403 || response.status === 429) { limited = true; throw new Error("rate limited"); }
  limited = false;
  return response.json();
}

function analyse(name, run, jobs) {
  const out = { name, title: TITLES[name], state: "waiting", percent: 0, stage: "Queued on GitHub", stages: [], tasks: 0, elapsed: 0, feed: [], apk: null, error: null, note: "" };
  const job = jobs.find((j) => j.name.toLowerCase().startsWith(name));
  if (!job) return out;
  const now = Date.now() / 1000;
  const steps = job.steps.filter((s) => !["Set up job", "Complete job"].includes(s.name) && !s.name.startsWith("Post "));
  const total = steps.reduce((n, s) => n + (WEIGHT[s.name] || 1), 0) || 1;
  let gained = 0, current = null;
  const feed = [];
  for (const step of steps) {
    const weight = WEIGHT[step.name] || 1;
    const began = secs(step.started_at), ended = secs(step.completed_at);
    if (step.status === "completed") {
      if (step.conclusion === "skipped") { out.stages.push({ label: step.name, state: "todo" }); continue; }
      const ok = step.conclusion === "success";
      if (ok) gained += weight;
      out.stages.push({ label: step.name, state: ok ? "done" : "failed" });
      feed.push(`> ${ok ? "OK  " : "FAIL"} ${step.name} (${Math.round((ended || now) - (began || now))}s)`);
    } else if (step.status === "in_progress") {
      gained += weight * Math.min(0.95, Math.max(0, (now - (began || now)) / (EXPECTED[step.name] || 45)));
      current = step.name;
      out.stages.push({ label: step.name, state: "active" });
      feed.push(`> RUN  ${step.name} ...`);
    } else out.stages.push({ label: step.name, state: "todo" });
  }
  const started = secs(job.started_at), finished = secs(job.completed_at);
  out.feed = feed.slice(-9);
  out.tasks = out.stages.filter((s) => s.state === "done").length;
  out.percent = Math.round((100 * gained) / total);
  out.elapsed = started ? Math.round((finished || now) - started) : 0;
  if (job.status === "queued") Object.assign(out, { state: "waiting", stage: "Waiting for a GitHub machine", percent: 0 });
  else if (job.status === "in_progress") Object.assign(out, { state: "running", stage: current || "Working", percent: Math.min(out.percent, 97) });
  else if (job.conclusion === "success") {
    Object.assign(out, { state: "done", percent: 100, stage: "Build complete" });
    out.apk = { file: `civicloop-${name}-release.apk`, mb: 0, url: `https://github.com/${REPO}/releases/download/apk-latest/civicloop-${name}-release.apk` };
  } else {
    const bad = (steps.find((s) => s.conclusion === "failure") || {}).name || "a step";
    Object.assign(out, { state: "failed", stage: "Build failed", error: `The step "${bad}" failed. Open the run on GitHub for the full log: ${run.html_url}` });
  }
  return out;
}

async function loadStatus() {
  const { workflow_runs: runs } = await gh("/actions/workflows/android-apks.yml/runs?per_page=1");
  if (!runs.length) return { apps: [], host: "", source: "NO BUILDS YET" };
  const run = runs[0];
  const { jobs } = await gh(`/actions/runs/${run.id}/jobs`);
  return { apps: ["crew", "resident"].map((n) => analyse(n, run, jobs)), run, source: `GITHUB RUN #${run.run_number}` };
}
