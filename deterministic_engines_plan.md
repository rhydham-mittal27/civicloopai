# Deterministic Duplicate, Risk, and Routing Engine Plan

## 1. Goal

Implement transparent baseline engines for the three core intelligence decisions in the CivicLoopAI PPT:

1. Detect likely duplicate waste reports.
2. Estimate explainable hotspot risk.
3. Recommend a capacity-aware collection route.

These engines must be deterministic, versioned, reproducible, and usable without external AI or ML services. Their outputs become the baseline against which Gemini, open-weight models, and future trained models are evaluated.

## 2. Current State and Target

### Current state

- `DuplicateDetectionService` uses a small exact-match heuristic for description, time, and category.
- `HotspotRiskService` calculates a fixed weighted score from nearby history and severity.
- `RoutePlanningService` requires an injected routing adapter and does not yet provide a local deterministic route algorithm.

### Target state

Add an engine module with pure functions and versioned configuration:

```text
civicloop/
  engines/
    __init__.py
    duplicate.py
    risk.py
    routing.py
    common.py
```

The application services should orchestrate repositories and persistence. Engines should only calculate results from explicit inputs and should not access SQLAlchemy sessions.

## 3. Shared Determinism Rules

- Normalize all timestamps to UTC before comparison.
- Round geographic distances only at presentation time, not during scoring.
- Sort all input records by stable ID and timestamp before processing.
- Use explicit versions such as `duplicate-baseline-1`, `risk-baseline-1`, and `route-baseline-1`.
- Use stable tie-breakers: score descending, then incident ID ascending.
- Avoid random sampling, unseeded model calls, current-time-dependent behavior, and unordered set iteration.
- Persist input configuration, factors, and engine version with every output.
- Reject invalid coordinates, negative volumes, invalid timestamps, and NaN/Infinity numeric values.

## 4. Shared Geographic Utilities

### `haversine_km(origin, destination)`

Calculate great-circle distance from latitude/longitude pairs using the Haversine formula:

```text
lat1, lon1, lat2, lon2 -> radians
a = sin((lat2-lat1)/2)^2 + cos(lat1) * cos(lat2) * sin((lon2-lon1)/2)^2
c = 2 * atan2(sqrt(a), sqrt(1-a))
distance_km = earth_radius_km * c
```

Use an earth radius of `6371.0088 km` and validate coordinates before calculating.

### `normalize_text(value)`

- Convert to Unicode casefolded text.
- Trim whitespace.
- Replace punctuation with spaces.
- Collapse repeated whitespace.
- Keep a token set for Jaccard comparison.

### `time_decay(age_days, half_life_days)`

```text
decay = 0.5 ** (max(age_days, 0) / half_life_days)
```

## 5. Deterministic Duplicate Engine

### Purpose

Identify candidate reports that likely describe the same physical waste incident without merging or deleting the source incidents.

### Inputs

- Source incident: coordinates, description, occurred timestamp
- Candidate incidents within a geographic search radius
- Latest analysis category and severity, when available
- Configuration version

### Configuration

```text
version: duplicate-baseline-1
radius_km: 0.25
time_window_hours: 24
candidate_limit: 50
threshold: 0.65
weights:
  distance: 0.35
  time: 0.25
  text: 0.25
  category: 0.15
```

### Feature scores

1. **Distance score**

```text
distance_score = max(0, 1 - distance_km / radius_km)
```

2. **Time score**

```text
time_score = max(0, 1 - abs(time_difference_hours) / time_window_hours)
```

3. **Text score**

```text
text_score = jaccard(normalize_text(source), normalize_text(candidate))
```

4. **Category score**

```text
category_score = 1.0 when both categories exist and match, otherwise 0.0
```

### Final score

```text
similarity =
  0.35 * distance_score +
  0.25 * time_score +
  0.25 * text_score +
  0.15 * category_score
```

Return a candidate when `similarity >= threshold`. Return candidate ID, score, feature breakdown, and engine version.

### Service integration

`DuplicateDetectionService.find_candidates` should:

1. Load the source incident through `IncidentRepository.get`.
2. Load nearby records through `IncidentRepository.list_for_location` or a geographic repository query.
3. Load latest analysis through `AnalysisRepository.latest_for_incident`.
4. Call the pure duplicate engine.
5. Return sorted candidate results.

`create_candidate_cluster` should persist only selected candidates through `DuplicateClusterRepository.add` and `add_member`. Supervisor confirmation remains separate.

### Duplicate engine tests

- Identical reports at the same location and time score above threshold.
- Reports outside the radius are excluded.
- Reports outside the time window are excluded.
- Punctuation and case do not change equivalent text scores.
- Missing analysis does not prevent text/location matching.
- Results have stable ordering for equal scores.
- Source incidents are never deleted or mutated.

## 6. Deterministic Risk Engine

### Purpose

Estimate near-term waste accumulation risk with visible factors instead of an opaque prediction.

### Inputs

- Target incident
- Nearby incident history
- Latest analysis severity
- Optional contextual signals such as sensor readings or service frequency
- Evaluation cutoff timestamp
- Configuration version

### Configuration

```text
version: risk-baseline-1
history_radius_km: 0.5
history_window_days: 90
recent_window_days: 30
weights:
  recurrence: 0.35
  recency: 0.25
  severity: 0.25
  unresolved: 0.15
```

### Features

1. **Recurrence**

Count distinct historical incidents within the radius and history window, capped at `10`:

```text
recurrence = min(distinct_incidents / 10, 1)
```

2. **Recency**

Sum time-decayed historical incidents and normalize to `0..1`:

```text
recency = min(sum(time_decay(age_days, 30)) / 5, 1)
```

3. **Severity**

```text
low=0.2, medium=0.5, high=0.8, critical=1.0, unknown=0.2
```

4. **Unresolved**

```text
unresolved = count(open incidents in radius) / max(count(all incidents in radius), 1)
```

### Final score

```text
score = min(1,
  0.35 * recurrence +
  0.25 * recency +
  0.25 * severity +
  0.15 * unresolved
)
```

Confidence is a separate value based on data completeness:

```text
confidence = available_features / expected_features
```

Persist the score, confidence, feature values, cutoff time, and engine version in `RiskAssessment`.

### Service integration

`HotspotRiskService.calculate_risk` should:

1. Load the incident through `IncidentRepository.get`.
2. Load history through a deterministic geographic/time query.
3. Load analysis through `AnalysisRepository.latest_for_incident`.
4. Call the pure risk engine with a fixed evaluation timestamp.
5. Persist through `RiskAssessmentRepository.add`.
6. Audit the engine version and score factors.

### Risk engine tests

- Empty history produces a low deterministic score.
- Repeated nearby incidents increase recurrence.
- Older incidents contribute less than recent incidents.
- Critical severity increases score predictably.
- Open incidents affect unresolved risk.
- Same inputs and cutoff timestamp produce byte-equivalent output.
- Missing optional context reduces confidence, not score validity.
- Scores and confidence remain within `0..1`.

## 7. Deterministic Routing Engine

### Purpose

Produce a capacity-aware route locally without requiring a commercial routing provider. A provider adapter can later replace or enrich this baseline.

### Inputs

- Approved work orders
- Incident coordinates
- Estimated waste volume per order
- Vehicle capacity
- Optional depot/start coordinate
- Operational constraints

### Validation

- Every work order exists and is `APPROVED`.
- Every work order has a valid incident coordinate.
- Every estimated volume is non-negative.
- Total volume does not exceed vehicle capacity.
- Vehicle capacity is positive.
- Duplicate work-order IDs are rejected.

### Baseline algorithm

Use a deterministic nearest-neighbor route:

1. Start at the configured depot, or the first stop selected by highest priority and lowest stable ID.
2. From the current location, select the unvisited stop with the smallest Haversine distance.
3. Break equal-distance ties by priority descending, then work-order ID ascending.
4. Continue until all stops are visited.
5. Add the return-to-depot distance when a depot is configured.
6. Estimate duration from distance and configured average speed.

This is a baseline, not a guarantee of global optimality. It must expose its assumptions.

### Outputs

```text
engine_version
ordered work-order IDs
ordered coordinates
planned volume
estimated_distance_km
estimated_duration_minutes
baseline assumptions
constraint checks
```

Persist the result in `RoutePlan` and `RouteStop` only after supervisor approval workflow allows it.

### Optional improvement pass

After nearest-neighbor construction, allow a deterministic 2-opt pass:

- Evaluate every valid edge reversal in stable index order.
- Keep only strictly shorter routes.
- Stop when no improvement remains or `max_iterations` is reached.
- Never violate capacity or fixed stop constraints.

The improvement pass must have its own engine version, for example `route-baseline-2opt-1`.

### Service integration

`RoutePlanningService.build_route` should:

1. Authorize the supervisor.
2. Load work orders through `WorkOrderRepository.get`.
3. Load incidents through `IncidentRepository.get`.
4. Call the deterministic routing engine when no external adapter is configured.
5. Compare the result with the simple baseline metrics.
6. Persist through `RoutePlanRepository.add` and `add_stop`.
7. Record engine version and constraints in the audit event.

External routing providers may be used as a comparison, but provider failure must not prevent the local baseline from operating.

### Routing engine tests

- Empty stop list returns a valid zero-distance route or a clear validation error, according to API policy.
- Capacity overflow is rejected before route calculation.
- Nearest stop ordering is correct.
- Equal distances use stable priority and ID tie-breakers.
- Depot return distance is included when configured.
- Negative and invalid volumes are rejected.
- Same inputs produce the same ordered stops and distance.
- A 2-opt pass never increases route distance.

## 8. Evaluation and Baselines

Store baseline outputs with the same fixtures used to evaluate AI/ML alternatives.

### Duplicate metrics

- Candidate precision and recall against labeled duplicate pairs
- False merge rate
- Supervisor confirmation rate

### Risk metrics

- Ranking precision at `k`
- Recall of incidents that recur within the evaluation window
- Calibration by confidence bucket
- Score stability between runs

### Routing metrics

- Route distance versus naive input order
- Route duration estimate
- Capacity violations, expected zero
- Average supervisor edits
- Provider route distance versus deterministic route distance

Every evaluation run must record:

- Dataset version
- Engine versions
- Configuration values
- Evaluation cutoff timestamp
- Metric outputs
- Baseline comparison

## 9. Delivery Sequence

1. Add shared geographic, text, time, and numeric validation utilities.
2. Implement pure duplicate scoring with unit tests.
3. Replace duplicate service heuristics with the versioned engine.
4. Implement pure risk scoring with fixed cutoff timestamps.
5. Replace risk service arithmetic and persist factor breakdowns.
6. Implement nearest-neighbor routing and capacity validation.
7. Add deterministic 2-opt as an optional versioned improvement.
8. Add engine fixtures and evaluation metrics.
9. Connect worker job types to the three engines.
10. Compare AI/ML alternatives against these baselines during the pilot.

## 10. Acceptance Criteria

- All three engines run without network access or model credentials.
- Same inputs, configuration, and cutoff produce identical results.
- Every result contains an engine version and explainable factors or assumptions.
- Duplicate detection never deletes or silently merges source incidents.
- Risk scores and confidence are bounded and auditable.
- Routing rejects invalid work orders and capacity overflow before persistence.
- Route ordering is stable and provider-independent for the deterministic baseline.
- Baseline fixtures and metrics are reproducible in CI.
- Future AI/ML implementations can be evaluated against these outputs without changing the service or repository contracts.