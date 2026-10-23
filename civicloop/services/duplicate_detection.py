from __future__ import annotations

from collections.abc import Sequence

from civicloop.models import DuplicateCluster, UserRole
from civicloop.embeddings import default_embedder
from civicloop.engines.duplicate import DuplicateEngine, DuplicateMatch
from civicloop.repositories import (
    AnalysisRepository,
    AuditEventRepository,
    DuplicateClusterRepository,
    IncidentRepository,
    UserRepository,
)
from civicloop.services.common import NotFoundError, record_audit, require_user


class DuplicateDetectionService:
    def __init__(
        self,
        clusters: DuplicateClusterRepository,
        incidents: IncidentRepository,
        analyses: AnalysisRepository,
        users: UserRepository,
        audit: AuditEventRepository,
        engine: DuplicateEngine | None = None,
    ) -> None:
        self.clusters = clusters
        self.incidents = incidents
        self.analyses = analyses
        self.users = users
        self.audit = audit
        # load=False: never block a request on downloading a model; startup warms it in the background.
        self.engine = engine or DuplicateEngine(embedder=default_embedder(load=False))

    def find_matches(
        self, incident_id: str, radius_degrees: float = 0.01, limit: int = 50
    ) -> list[DuplicateMatch]:
        incident = self.incidents.get(incident_id)
        if incident is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        source_analysis = self.analyses.latest_for_incident(incident_id)
        candidates = list(self.incidents.list_for_location(
            incident.latitude,
            incident.longitude,
            radius_degrees=min(radius_degrees, self.engine.config.radius_km / 111),
            limit=limit,
        ))
        analyses = {str(candidate.id): self.analyses.latest_for_incident(str(candidate.id)) for candidate in candidates}
        return self.engine.find(incident, candidates, source_analysis, analyses)

    def find_candidates(
        self, incident_id: str, radius_degrees: float = 0.01, limit: int = 50
    ) -> list[tuple[str, float]]:
        matches = self.find_matches(incident_id, radius_degrees, limit)
        return [(match.incident_id, match.similarity_score) for match in matches]

    def create_candidate_cluster(
        self, incident_id: str, candidate_scores: Sequence[tuple[str, float]]
    ) -> DuplicateCluster:
        if self.incidents.get(incident_id) is None:
            raise NotFoundError(f"Incident not found: {incident_id}")
        cluster = self.clusters.add(DuplicateCluster(confirmed=False))
        self.clusters.add_member(cluster.id, incident_id, 1.0)
        for candidate_id, score in candidate_scores:
            if self.incidents.get(candidate_id) is not None:
                self.clusters.add_member(cluster.id, candidate_id, score)
        record_audit(self.audit, None, "duplicate_cluster", cluster.id, "created")
        return cluster

    def confirm_cluster(self, cluster_id: str, supervisor_id: str) -> DuplicateCluster:
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        cluster = self.clusters.confirm(cluster_id, supervisor_id)
        record_audit(
            self.audit, supervisor_id, "duplicate_cluster", cluster_id, "confirmed"
        )
        return cluster

    def reject_cluster(self, cluster_id: str, supervisor_id: str) -> DuplicateCluster:
        require_user(self.users, supervisor_id, {UserRole.SUPERVISOR, UserRole.ADMIN})
        cluster = self.clusters.reject(cluster_id)
        record_audit(
            self.audit, supervisor_id, "duplicate_cluster", cluster_id, "rejected"
        )
        return cluster
