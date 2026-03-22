"""
Tests for the deps module: RunManager and singleton helpers.
"""


from stlc_platform.api.deps import RunManager


class TestRunManagerCreateRun:
    """create_run() creates and returns a run entry."""

    def test_returns_string_id(self):
        rm = RunManager()
        rid = rm.create_run("pipeline_a")
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_custom_run_id(self):
        rm = RunManager()
        rid = rm.create_run("pipeline_a", run_id="my-run-1")
        assert rid == "my-run-1"

    def test_run_is_pending(self):
        rm = RunManager()
        rid = rm.create_run("pipeline_a")
        run = rm.get_run(rid)
        assert run["status"] == "pending"

    def test_run_has_pipeline_name(self):
        rm = RunManager()
        rid = rm.create_run("my_pipeline")
        run = rm.get_run(rid)
        assert run["pipeline_name"] == "my_pipeline"

    def test_run_has_started_at(self):
        rm = RunManager()
        rid = rm.create_run("p")
        run = rm.get_run(rid)
        assert run["started_at"] is not None
        assert len(run["started_at"]) > 0

    def test_run_has_empty_stage_lists(self):
        rm = RunManager()
        rid = rm.create_run("p")
        run = rm.get_run(rid)
        assert run["stages_completed"] == []
        assert run["stages_failed"] == []
        assert run["stages_skipped"] == []


class TestRunManagerGetRun:
    """get_run() retrieves a run or returns None."""

    def test_returns_none_for_unknown(self):
        rm = RunManager()
        assert rm.get_run("does-not-exist") is None

    def test_returns_dict_for_known(self):
        rm = RunManager()
        rid = rm.create_run("p")
        run = rm.get_run(rid)
        assert isinstance(run, dict)
        assert run["run_id"] == rid


class TestRunManagerListRuns:
    """list_runs() returns all runs in reverse order."""

    def test_empty_initially(self):
        rm = RunManager()
        assert rm.list_runs() == []

    def test_returns_all_runs(self):
        rm = RunManager()
        rm.create_run("a")
        rm.create_run("b")
        rm.create_run("c")
        assert len(rm.list_runs()) == 3

    def test_most_recent_first(self):
        rm = RunManager()
        rm.create_run("a", run_id="first")
        rm.create_run("b", run_id="second")
        runs = rm.list_runs()
        assert runs[0]["run_id"] == "second"
        assert runs[1]["run_id"] == "first"


class TestRunManagerSetRunning:
    """set_running() updates status to 'running'."""

    def test_status_becomes_running(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.set_running(rid)
        assert rm.get_run(rid)["status"] == "running"


class TestRunManagerSetCompleted:
    """set_completed() updates status and records duration."""

    def test_status_becomes_completed(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.set_completed(rid, 5.678)
        run = rm.get_run(rid)
        assert run["status"] == "completed"

    def test_records_duration(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.set_completed(rid, 5.678)
        run = rm.get_run(rid)
        assert run["total_duration_seconds"] == 5.678

    def test_records_completed_at(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.set_completed(rid, 1.0)
        run = rm.get_run(rid)
        assert run["completed_at"] is not None


class TestRunManagerSetFailed:
    """set_failed() updates status, error message, and duration."""

    def test_status_becomes_failed(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.set_failed(rid, "boom", 0.1)
        assert rm.get_run(rid)["status"] == "failed"

    def test_records_error_message(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.set_failed(rid, "stage crashed", 0.5)
        assert rm.get_run(rid)["error_message"] == "stage crashed"

    def test_records_duration(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.set_failed(rid, "err", 2.345)
        assert rm.get_run(rid)["total_duration_seconds"] == 2.345


class TestRunManagerStoreArtifacts:
    """store_artifacts() attaches artifacts to a run."""

    def test_stores_artifacts(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.store_artifacts(rid, {"requirements": ["REQ-1", "REQ-2"]})
        run = rm.get_run(rid)
        assert run["artifacts"]["requirements"] == ["REQ-1", "REQ-2"]

    def test_merges_artifacts(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.store_artifacts(rid, {"a": 1})
        rm.store_artifacts(rid, {"b": 2})
        arts = rm.get_run(rid)["artifacts"]
        assert arts["a"] == 1
        assert arts["b"] == 2

    def test_noop_for_unknown_run(self):
        rm = RunManager()
        # Should not raise
        rm.store_artifacts("ghost", {"x": 1})


class TestRunManagerStoreMetadata:
    """store_metadata() attaches metadata to a run."""

    def test_stores_metadata(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.store_metadata(rid, {"pipeline_result": {"status": "ok"}})
        run = rm.get_run(rid)
        assert run["metadata"]["pipeline_result"]["status"] == "ok"

    def test_merges_metadata(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.store_metadata(rid, {"key1": "val1"})
        rm.store_metadata(rid, {"key2": "val2"})
        meta = rm.get_run(rid)["metadata"]
        assert meta["key1"] == "val1"
        assert meta["key2"] == "val2"

    def test_noop_for_unknown_run(self):
        rm = RunManager()
        rm.store_metadata("ghost", {"x": 1})


class TestRunManagerUpdateRun:
    """update_run() sets arbitrary fields."""

    def test_updates_current_stage(self):
        rm = RunManager()
        rid = rm.create_run("p")
        rm.update_run(rid, current_stage="bdd")
        assert rm.get_run(rid)["current_stage"] == "bdd"

    def test_noop_for_unknown_run(self):
        rm = RunManager()
        # Should not raise
        rm.update_run("ghost", status="running")
