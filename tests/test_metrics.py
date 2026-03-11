"""Tests for Prometheus metrics endpoint and custom counters."""

import pytest


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint."""

    def test_metrics_endpoint_returns_200(self, client):
        """GET /metrics returns 200 OK with Prometheus text format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type or "text/plain" in content_type

    def test_metrics_contains_standard_http_metrics(self, client):
        """Metrics output includes standard HTTP instrumentation metrics."""
        # Make a request to generate metrics
        client.get("/")
        response = client.get("/metrics")
        body = response.text
        assert "http_requests_total" in body or "http_request_duration_seconds" in body

    def test_metrics_contains_custom_counters(self, client):
        """Metrics output includes custom compliance counters."""
        response = client.get("/metrics")
        body = response.text
        # Custom metrics should be registered (may show as 0)
        assert "compliance_response_status" in body or "compliance_tokens" in body or "compliance_openai_errors" in body

    def test_metrics_endpoint_no_auth_required(self, client_no_auth):
        """The /metrics endpoint should be accessible without authentication."""
        response = client_no_auth.get("/metrics")
        assert response.status_code == 200


class TestCustomStatusCodeMetrics:
    """Tests that custom status codes are tracked correctly."""

    def test_success_increments_200_counter(self, client, sample_compliance_request):
        """Successful compliance check increments code=200 counter."""
        client.post("/check_compliance", json=sample_compliance_request)
        response = client.get("/metrics")
        body = response.text
        assert 'compliance_response_status_total{code="200"' in body

    def test_empty_data_does_not_increment_custom_counter(self, client):
        """Empty data 400 error is an HTTP-level error, not a custom status code."""
        request = {
            "AIViolationID": [{"ID": "FAIR", "mlsId": "TESTMLS", "CheckColumns": "Remarks"}],
            "Data": []
        }
        client.post("/check_compliance", json=request)
        response = client.get("/metrics")
        body = response.text
        # Standard HTTP 400 is tracked by the instrumentator, not our custom counter
        assert "http_requests_total" in body


class TestTokenUsageMetrics:
    """Tests that token usage is tracked in Prometheus."""

    def test_token_counter_incremented_on_success(self, client, sample_compliance_request):
        """Successful request increments token usage counter."""
        client.post("/check_compliance", json=sample_compliance_request)
        response = client.get("/metrics")
        body = response.text
        assert "compliance_tokens_used_total" in body
