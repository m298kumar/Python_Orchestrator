from fastapi.testclient import TestClient
from stlc_platform.api.deps import TestCaseStore
from stlc_platform.api.main import app
from stlc_platform.api.review_store import TestCaseReviewStore


class FakePersistentRag:
    def __init__(self):
        self.approved = {}

    def store_approved_tc(self, tc_dict, ac_type, test_type, domain="", human_approved=False):
        assert human_approved is True
        doc_id = f"rag-{tc_dict['run_id']}-{tc_dict['tc_id']}"
        self.approved[doc_id] = dict(tc_dict)
        return doc_id

    def delete_approved_tc(self, doc_id):
        self.approved.pop(doc_id, None)


def test_frontend_review_contract_persists_audit_and_promotes_exact_run(tmp_path, monkeypatch):
    store = TestCaseStore()
    common = {
        "tc_id": "TC-001",
        "req_id": "REQ-001",
        "title": "Reviewed test",
        "description": "Verify a concrete outcome",
        "preconditions": "A user exists",
        "test_type": "positive",
        "priority": "High",
        "steps": [{"action": "Perform action", "expected_result": "Outcome appears"}],
        "expected_outcome": "Outcome appears",
        "quality_score": 0.9,
        "quality_issues": [],
    }
    store.populate([common], run_id="run-one")
    store.populate([{**common, "title": "Second run"}], run_id="run-two")
    review_store = TestCaseReviewStore(tmp_path / "output" / "review" / "reviews.sqlite3")
    rag = FakePersistentRag()
    monkeypatch.setattr("stlc_platform.api.routes.test_cases.get_tc_store", lambda: store)
    monkeypatch.setattr("stlc_platform.api.routes.test_cases._review_store", review_store)
    monkeypatch.setattr("stlc_platform.api.routes.test_cases._get_rag_store", lambda: rag)

    response = TestClient(app).post(
        "/api/test-cases/runs/run-two/TC-001/approve",
        json={"reason": "Manually verified", "reviewer": "qa-user"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-two"
    assert payload["rag_example_id"] == "rag-run-two-TC-001"
    assert store.get("TC-001", "run-one")["status"] == "generated"
    assert review_store.latest("run-two", "TC-001")["reviewer"] == "qa-user"

    store.clear()
    store.populate([{**common, "title": "Second run"}], run_id="run-two")
    restored = TestClient(app).get(
        "/api/test-cases/TC-001", params={"run_id": "run-two"}
    )
    assert restored.json()["status"] == "approved"
    assert restored.json()["review_reason"] == "Manually verified"
