from stlc_platform.api.review_store import TestCaseReviewStore


def test_review_store_persists_latest_decision_across_instances(tmp_path):
    path = tmp_path / "review.sqlite3"
    tc = {"tc_id": "TC-1", "run_id": "run-1", "quality_score": 0.9, "quality_issues": []}
    first = TestCaseReviewStore(path)
    first.record(tc, "approved", reason="verified", reviewer="qa", rag_example_id="rag-1")

    reopened = TestCaseReviewStore(path)
    review = reopened.latest("run-1", "TC-1")

    assert review["status"] == "approved"
    assert review["rag_example_id"] == "rag-1"
    assert review["reason"] == "verified"


def test_runtime_review_store_consumes_configured_project_path(tmp_path, monkeypatch):
    from stlc_platform.api.routes import test_cases

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "stlc_config.yaml").write_text(
        "review:\n  sqlite_path: state/human-reviews.sqlite3\n", encoding="utf-8"
    )
    monkeypatch.setattr("stlc_platform.core.config_loader._find_project_root", lambda: tmp_path)
    monkeypatch.setattr(test_cases, "_review_store", None)

    store = test_cases._get_review_store()

    assert store.path == tmp_path / "state" / "human-reviews.sqlite3"
