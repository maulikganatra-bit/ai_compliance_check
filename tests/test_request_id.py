import re
from fastapi.testclient import TestClient


def test_request_id_in_response(client, sample_compliance_request):
    """POST /check_compliance returns a `request_id` in the body and header.

    Verifies:
    - Response JSON includes `request_id`.
    - Response header `X-Request-ID` exists.
    - Header and body values are identical.
    - The value looks like a UUID4 (basic format check).
    """
    response = client.post("/check_compliance", json=sample_compliance_request)
    assert response.status_code == 200

    data = response.json()

    # Body contains request_id
    assert "request_id" in data
    request_id_body = data["request_id"]

    # Header contains X-Request-ID
    assert "X-Request-ID" in response.headers
    request_id_header = response.headers["X-Request-ID"]

    # They should match
    assert request_id_body == request_id_header

    # Basic UUID format check (36 chars, 4 hyphens)
    assert isinstance(request_id_body, str)
    assert request_id_body.count("-") == 4
    assert len(request_id_body) == 36
