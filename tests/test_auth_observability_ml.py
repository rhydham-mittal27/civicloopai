import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from civicloop.auth import AuthenticationError, AuthenticationService, TokenAuthenticator, hash_password
from civicloop.evaluation_pipeline import EvaluationPipeline, EvaluationSample
from civicloop.ml import ModelMetadata, ModelRegistry
from civicloop.models import User, UserRole
from civicloop.observability import MetricsRegistry, current_request_id, observe_operation, request_context
from civicloop.db import init_db


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with Session(engine) as database_session:
        yield database_session


class FakeRunner:
    def predict(self, features):
        return features["prediction"]


def test_authentication_issues_and_validates_expiring_tokens(session):
    from civicloop.repositories import UserRepository

    user = UserRepository(session).add(User(name="Admin", email="auth@example.com", role=UserRole.ADMIN, password_hash=hash_password("correct horse battery")))
    service = AuthenticationService(UserRepository(session), TokenAuthenticator("a" * 32, ttl_seconds=60))
    token = service.login("auth@example.com", "correct horse battery")
    principal = service.authenticator.authenticate(f"Bearer {token}", now=100)

    assert principal.user_id == user.id
    assert principal.role == UserRole.ADMIN
    with pytest.raises(AuthenticationError):
        service.authenticator.authenticate(f"Bearer {token}x", now=100)
    expiring_token = service.authenticator.issue(user, now=100)
    with pytest.raises(AuthenticationError):
        service.authenticator.authenticate(f"Bearer {expiring_token}", now=161)


def test_observability_tracks_correlation_and_operation_metrics(caplog):
    metrics = MetricsRegistry()
    logger = logging.getLogger("test-observability")
    with request_context("request-123"):
        assert current_request_id() == "request-123"
        with caplog.at_level(logging.INFO):
            with observe_operation(metrics, logger, "analysis", provider="test"):
                pass

    snapshot = metrics.snapshot()
    assert any("operations_started" in key for key in snapshot["counters"])
    assert any("operation_duration_seconds" in key for key in snapshot["timings"])


def test_model_registry_and_evaluation_pipeline_are_reproducible():
    metadata = ModelMetadata("baseline", "1", "deterministic", "waste-analysis")
    registry = ModelRegistry()
    registry.register(metadata, FakeRunner())
    samples = [
        EvaluationSample("b", {"prediction": {"category": "plastic", "is_duplicate": False, "risk_score": 0.2}}, "plastic", False, False),
        EvaluationSample("a", {"prediction": {"category": "mixed", "is_duplicate": True, "risk_score": 0.9}}, "mixed", True, True),
    ]

    report = EvaluationPipeline().run("dataset-1", samples, metadata, registry.get("baseline", "1").runner)

    assert report.sample_count == 2
    assert report.metrics["category_accuracy"] == 1.0
    assert report.metrics["duplicate_precision"] == 1.0
    assert report.metrics["risk_precision_at_k"] == 0.5
    assert [row["sample_id"] for row in report.predictions] == ["a", "b"]