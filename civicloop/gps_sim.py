"""Drive demo vehicles around a city and report them like a real GPS tracker would.

    python -m civicloop.gps_sim --email supervisor@civic.test --password ... --vehicles 4

It signs in as a supervisor, makes (or re-keys) vehicles called "Demo truck N", then posts a fix every few
seconds to the same /telemetry/gps endpoint a hardware tracker uses. The trucks drive in straight lines
between demo sites with a short stop at each, so the movement is simulated and does not follow roads.
Stop it with Ctrl+C. Re-keying only touches vehicles named "Demo truck".
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from civicloop.demo import DEPOT, SITES
from civicloop.services.fleet import haversine_km

PREFIX = "Demo truck"


def call(base: str, method: str, path: str, body: dict | None = None, token: str | None = None, key: str | None = None) -> dict | list:
    request = urllib.request.Request(f"{base}/api/v1{path}", method=method, data=json.dumps(body).encode() if body is not None else None)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if key:
        request.add_header("X-Device-Key", key)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read() or "null")
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{method} {path} failed: {error.code} {error.read().decode()[:200]}") from error


class Truck:
    def __init__(self, label: str, key: str, rng: random.Random, waypoints: list[tuple[float, float]], speed_kmh: float) -> None:
        self.label, self.key, self.rng = label, key, rng
        self.route = waypoints
        self.leg = 0
        self.lat, self.lon = waypoints[0]
        self.speed = speed_kmh
        self.pause_until = 0.0
        self.heading = 0.0

    def step(self, seconds: float, now: float) -> tuple[float, float, float, float]:
        """Advance by `seconds`. Returns (lat, lon, speed_kmh, heading)."""
        if now < self.pause_until:
            return self.lat, self.lon, 0.0, self.heading
        target = self.route[(self.leg + 1) % len(self.route)]
        remaining = haversine_km(self.lat, self.lon, target[0], target[1])
        travel = (self.speed * self.rng.uniform(0.7, 1.15)) * seconds / 3600
        if travel >= remaining:
            self.lat, self.lon = target
            self.leg = (self.leg + 1) % len(self.route)
            self.pause_until = now + self.rng.uniform(25, 70)  # collecting at the site
            return self.lat, self.lon, 0.0, self.heading
        fraction = travel / remaining
        dlat, dlon = target[0] - self.lat, target[1] - self.lon
        self.heading = (math.degrees(math.atan2(dlon * math.cos(math.radians(self.lat)), dlat)) + 360) % 360
        self.lat, self.lon = self.lat + dlat * fraction, self.lon + dlon * fraction
        return self.lat, self.lon, self.speed, self.heading


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--vehicles", type=int, default=4)
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between fixes")
    parser.add_argument("--speedup", type=float, default=1.0, help="multiply driving speed to see movement sooner")
    parser.add_argument("--seed", type=int, default=3)
    args = parser.parse_args()

    token = call(args.api, "POST", "/auth/login", {"email": args.email, "password": args.password})["access_token"]
    existing = {v["label"]: v for v in call(args.api, "GET", "/vehicles", token=token)}
    workers = call(args.api, "GET", "/users?role=sanitation_worker", token=token)
    rng = random.Random(args.seed)
    trucks: list[Truck] = []
    for n in range(1, args.vehicles + 1):
        label = f"{PREFIX} {n}"
        if label in existing:
            key = call(args.api, "POST", f"/vehicles/{existing[label]['id']}/device-key", token=token)["device_key"]
        else:
            driver = workers[(n - 1) % len(workers)]["id"] if workers and n <= len(workers) else None
            key = call(args.api, "POST", "/vehicles", {"label": label, "registration": f"CH01 CL {1000 + n}", "driver_id": driver}, token=token)["device_key"]
        sites = rng.sample(SITES, k=min(5, len(SITES)))
        route = [DEPOT] + [(s[1], s[2]) for s in sites]
        trucks.append(Truck(label, key, rng, route, speed_kmh=rng.uniform(18, 32) * args.speedup))
        print(f"{label}: {len(route)} stops")

    print(f"Reporting every {args.interval:.0f}s to {args.api}. Ctrl+C to stop.")
    last = time.time()
    try:
        while True:
            time.sleep(args.interval)
            now = time.time()
            for truck in trucks:
                lat, lon, speed, heading = truck.step(now - last, now)
                noise = 0.00003  # about 3 m of GPS jitter
                call(
                    args.api,
                    "POST",
                    "/telemetry/gps",
                    {
                        "lat": lat + rng.uniform(-noise, noise),
                        "lon": lon + rng.uniform(-noise, noise),
                        "speed_kmh": round(speed, 1),
                        "heading": round(heading, 0),
                        "accuracy_m": round(rng.uniform(4, 12), 1),
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    },
                    key=truck.key,
                )
            last = now
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
