"""
Tests for the unified config loader.
"""

import os
import pytest
from stlc_platform.core.config_loader import load_config, AppConfig


class TestConfigLoader:
    def test_load_returns_app_config(self):
        cfg = load_config()
        assert isinstance(cfg, AppConfig)

    def test_default_values(self):
        cfg = load_config()
        assert cfg.ollama.base_url == os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
        assert cfg.max_test_cases_per_requirement >= 1

    def test_config_has_ollama(self):
        cfg = load_config()
        assert hasattr(cfg, "ollama")
        assert hasattr(cfg.ollama, "model")
        assert hasattr(cfg.ollama, "temperature")

    def test_config_has_chromadb(self):
        cfg = load_config()
        assert hasattr(cfg, "chromadb")
        assert hasattr(cfg.chromadb, "persist_directory")

    def test_config_has_output(self):
        cfg = load_config()
        assert hasattr(cfg, "output")
        assert cfg.output.csv_filename == "test_cases.csv"

    def test_config_has_zephyr(self):
        cfg = load_config()
        assert hasattr(cfg, "zephyr")
        assert cfg.zephyr.default_status in ("Draft", "Approved")

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "test-model:latest")
        cfg = load_config()
        assert cfg.ollama.model == "test-model:latest"
