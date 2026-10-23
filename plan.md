# CivicLoopAI Implementation Plan

## 1. Current Project State

- The workspace currently contains only `Code5urge_CivicLoopAI.pptx`.
- No application code, database schema, tests, deployment configuration, sample dataset, or environment template exists yet.
- The presentation describes a proposed Chandigarh pilot, not a validated production system.
- The Technical Architecture slide does not contain readable architecture details, so the architecture below is an implementation proposal.

## 2. Product Goal

Build a human-supervised waste-management workflow that turns citizen or field-worker reports into prioritized, actionable, and verifiable sanitation work:

`Observe -> Understand -> Predict -> Prioritize -> Act -> Verify -> Learn`

The MVP should include the complete PPT vision: an end-to-end pilot-ready product, reusable model integrations, evaluation, scale-up preparation, and the proposed business and funding pathways. Predictive or operational impact must still be presented as a hypothesis until evaluated against a baseline.

## 3. MVP Scope

### Included

1. **Incident reporting**
   - Upload a waste-site photograph.
   - Capture description, GPS coordinates, timestamp, and reporter type.
   - Validate image type/size and required location metadata.
   - Create an incident in a pending-analysis state.

2. **AI-assisted analysis**
   - Send image and text to a Gemini adapter.
   - Return schema-validated fields such as waste category, severity indicators, confidence, and extracted details.
   - Keep the raw model response and normalized result for auditability.
   - Expose an interface for an open-weight vision-model adapter without coupling the workflow to one provider.

3. **Duplicate detection and clustering**
   - Identify likely duplicates using geographic proximity, time window, textual similarity, and image/model signals.
   - Group candidate reports while allowing a supervisor to confirm or reject the grouping.

4. **Hotspot risk scoring**
   - Calculate an explainable risk score from recurrence, recent incident count, severity, time decay, and available contextual signals.
   - Display score components and confidence rather than only a single opaque number.
   - Start with a deterministic baseline; add a trained predictive model only after sufficient labeled data exists.

5. **Supervisor prioritization**
   - Provide a ranked incident queue with filters for status, severity, location, and risk.
   - Allow supervisors to approve, edit, defer, merge, or reject recommendations.
   - Record the actor, decision, timestamp, and reason for every human override.

6. **Route recommendation**
   - Recommend a collection sequence using incident coordinates, vehicle capacity, estimated waste volume, travel distance, and operational constraints.
   - Present the recommendation for approval; do not dispatch automatically in the MVP.
   - Compare route distance/time with a simple baseline.

7. **Cleanup verification**
   - Let sanitation workers upload an after-cleanup photograph linked to an approved incident.
   - Store before/after evidence and a resolution record.
   - Use basic rule-based checks for clear cases and flag uncertain cases for supervisor review.
   - Do not represent a report as verified solely because it was marked closed.

8. **Evaluation and reproducibility**
   - Include a small documented sample dataset and repeatable test cases.
   - Measure extraction quality, duplicate precision/recall, risk-ranking quality, route efficiency, workflow reliability, and verified closure rate.
   - Provide `.env.example`, setup instructions, dependency documentation, and secret-free examples.

9. **Open-source and reusable engineering**
   - Keep the application modular so Gemini and open-weight models can be compared without redesigning the workflow.
   - Separate original application code from third-party models and services.
   - Publish reusable schemas, adapter interfaces, evaluation fixtures, and setup documentation.

10. **Pilot delivery**
   - Support the proposed 8–12 week Chandigarh pilot, subject to stakeholder access, data availability, and operational approval.
   - Establish a historical or initial-period baseline before measuring improvement.
   - Validate workflow usability, data quality, and operational fit before scale decisions.

11. **Scale-up and business readiness**
   - Provide configuration for adapting workflows to multiple cities and geographies.
   - Include SaaS-oriented dashboards, analytics, and incident management capabilities.
   - Document implementation-pilot setup and workflow configuration.
   - Define integration points for enterprise municipal systems.
   - Document optional IoT sensor integration for cases where it is economically justified.
   - Record potential funding pathways: civic innovation programs, sustainability initiatives, and CSR-supported pilots.

### MVP Boundaries and Dependencies

- Vehicle dispatch and enforcement remain approval-controlled; the MVP must not perform them automatically.
- Multi-city support means configurable architecture and documented adaptation points, not that every city is fully deployed.
- IoT support means an integration interface and documented optional path; sensor procurement and installation require separate approval.
- Municipal integrations require confirmed APIs, data contracts, security review, and stakeholder access.
- Model training remains dependent on labeled data; the MVP must support baseline and adapter comparison first.
- Fixed improvement percentages are not acceptance criteria until pilot data supports them.

## 4. Proposed Technical Architecture

### Components

- **Web client:** Reporter, supervisor, and sanitation-worker views with role-based access.
- **API service:** Incident, analysis, clustering, scoring, route, verification, audit, and evaluation endpoints.
- **Relational database:** Users, incidents, locations, analyses, duplicate groups, risk scores, work orders, evidence, decisions, and audit events.
- **Object storage:** Original reports, before/after images, and model artifacts. Store references and hashes in the database.
- **Background worker:** Asynchronous image analysis, duplicate matching, risk recalculation, and route generation.
- **AI provider adapters:** Gemini implementation plus a documented open-weight adapter contract.
- **Routing adapter:** A replaceable routing provider with a deterministic fallback for local demos.
- **Evaluation module:** Dataset loading, metric calculation, baseline comparison, and result export.

### Suggested Flow

1. Client uploads a report to the API.
2. API validates metadata, stores the image, and creates an incident.
3. Worker runs the selected AI adapter and validates its structured output.
4. Deduplication and risk-scoring services update the incident and its cluster.
5. Supervisor reviews the ranked queue and approves or changes a work order.
6. Route service produces an explainable collection sequence.
7. Worker submits after-cleanup evidence.
8. Verification service assigns verified, uncertain, or rejected status.
9. All state changes are written to an audit trail and included in evaluation data.

### Initial Data Entities

- `User` and `Role`
- `Incident`
- `MediaAsset`
- `AnalysisResult`
- `DuplicateCluster`
- `RiskAssessment`
- `WorkOrder`
- `RoutePlan` and `RouteStop`
- `VerificationRecord`
- `AuditEvent`
- `EvaluationRun`

## 5. Delivery Phases

### Phase 0: Discovery and Contracts

- Confirm pilot users, roles, workflow states, and municipal constraints.
- Define incident, analysis, evidence, and audit schemas.
- Decide the initial stack, storage approach, routing provider, and authentication method.
- Obtain consent, privacy, retention, and image-handling requirements.

**Exit:** API contract, state machine, data dictionary, threat/privacy checklist, and sample fixtures.

### Phase 1: Vertical Prototype

- Create the application skeleton and local development setup.
- Implement report submission, image storage, incident list, and incident detail view.
- Add seeded sample incidents and basic role-aware screens.

**Exit:** A user can submit a report and a supervisor can inspect it end to end without AI.

### Phase 2: Understand and Predict

- Implement Gemini structured extraction with schema validation and failure handling.
- Add provider-independent model interfaces.
- Implement duplicate candidates and human confirmation.
- Implement deterministic, explainable hotspot scoring.

**Exit:** A report produces inspectable analysis, duplicate candidates, and a reproducible risk score.

### Phase 3: Prioritize and Act

- Build the ranked supervisor queue and override/audit flow.
- Add capacity-aware route recommendation and baseline comparison.
- Add work-order states and worker-facing task view.

**Exit:** A supervisor can approve a work order and generate a reviewed collection sequence.

### Phase 4: Verify and Evaluate

- Add after-cleanup evidence upload and verification rules.
- Add uncertain-case review and auditable closure.
- Add evaluation scripts, metrics, fixtures, and result reporting.
- Test failure paths, permission boundaries, and malformed model output.

**Exit:** The full loop reaches an evidence-backed resolution and produces measurable evaluation results.

### Phase 5: Pilot, Scale, and Business Readiness

- Run the 8–12 week Chandigarh pilot after stakeholder access, data availability, and operational approval are confirmed.
- Establish a historical or initial-period baseline.
- Monitor resolution time, recurrence, duplicate clustering, route efficiency, and verified closure.
- Document findings and decide whether expansion is justified.
- Validate configurable workflows for additional cities.
- Package implementation-pilot, SaaS, enterprise-integration, optional-IoT, and funding-pathway materials.

## 6. Acceptance Criteria

- A report cannot be created without required metadata and a valid image.
- Every AI result is schema-validated, confidence-labeled, versioned, and traceable to its input.
- Supervisors can see why an incident is ranked and can override every automated recommendation.
- Duplicate grouping never deletes source reports and supports manual correction.
- Route recommendations show constraints, assumptions, and a baseline comparison.
- A case is not verified without linked before/after evidence or an explicit human decision.
- Role permissions prevent unauthorized changes to incidents, work orders, and verification status.
- Secrets are excluded from source control and setup works from `.env.example`.
- Tests cover core state transitions, scoring, duplicate matching, permission checks, and invalid AI responses.
- Evaluation outputs are reproducible from documented fixtures and commands.

## 7. Key Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Insufficient local training or validation data | Start with deterministic rules, document assumptions, and label a pilot dataset before training. |
| Hallucinated or inconsistent model output | Use strict schemas, confidence thresholds, retries, logging, and human review. |
| False duplicate merges | Present candidates for confirmation and preserve every original report. |
| Biased or misleading hotspot scores | Show score factors, monitor by area/time, and validate against a baseline. |
| Poor image quality or changing conditions | Require quality checks and route uncertain cases to review. |
| Privacy or sensitive location data | Define consent, access control, retention, redaction, and storage policy before pilot use. |
| Routing provider unavailable or inaccurate | Use a provider adapter and deterministic fallback for demos. |
| Operational resistance | Involve supervisors and workers in workflow testing before measuring impact. |

## 8. Open Questions Before Implementation

1. Who are the pilot users, and what permissions does each role require?
2. What data source and retention policy will apply to resident photographs and GPS data?
3. Which Chandigarh municipal systems, map data, and routing services are available?
4. What vehicle capacities, collection constraints, and service windows should routing support?
5. What does “sufficient” before/after evidence mean for each waste category?
6. Which language(s) must descriptions and worker interfaces support?
7. What baseline data is available, and how will labels for duplicates, risk, and closure be created?
8. What are the required latency, cost, and availability limits for Gemini calls?
9. Which open-weight models are acceptable, and what hardware/license constraints apply?
10. Which success thresholds justify moving from prototype to controlled pilot?

## 9. Recommended First Build Order

1. Create the repository structure, local setup, `.env.example`, and README.
2. Define the database schema and incident state machine.
3. Build report submission and supervisor incident views with seeded data.
4. Add the AI adapter contract and Gemini implementation behind a feature flag.
5. Add deterministic duplicate detection and explainable risk scoring.
6. Implement supervisor approval, work orders, and route recommendations.
7. Implement before/after verification and audit history.
8. Add evaluation fixtures, metrics, automated tests, and pilot-readiness documentation.

## 10. Source Notes

This plan is derived from `Code5urge_CivicLoopAI.pptx`. The deck describes hypotheses and a proposed pilot; it does not provide verified Chandigarh statistics, a concrete technical stack, a data schema, or an implementation baseline. Those items should be confirmed before production claims or pilot commitments.