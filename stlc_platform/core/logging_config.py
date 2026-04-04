"""
Logging Configuration Loader
============================
Loads logging configuration from YAML file and applies it.
"""

import logging
import logging.config
import os
from pathlib import Path

import yaml


def setup_logging(
    default_path="config/logging.yaml", default_level=logging.INFO, env_key="LOG_CFG"
):
    """Setup logging configuration from YAML file."""
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value

    # Convert to absolute path if needed
    if not os.path.isabs(path):
        # Assume path is relative to project root
        project_root = Path(__file__).parent.parent.parent
        path = project_root / path

    if os.path.exists(path):
        try:
            with open(path, "rt") as f:
                config = yaml.safe_load(f.read())
            # Ensure logs directory exists before configuring handlers that write to it
            project_root = Path(__file__).parent.parent.parent
            log_dir = project_root / "logs"
            log_dir.mkdir(exist_ok=True)
            # Resolve relative filenames in file handlers to absolute paths
            for handler in (config.get("handlers") or {}).values():
                fn = handler.get("filename")
                if fn and not os.path.isabs(fn):
                    handler["filename"] = str(project_root / fn)
            logging.config.dictConfig(config)
        except Exception as e:
            print(f"Error loading logging config from {path}: {e}")
            print("Using basic logging configuration")
            logging.basicConfig(level=default_level)
    else:
        print(f"Logging config file not found at {path}")
        print("Using basic logging configuration")
        logging.basicConfig(level=default_level)


def get_logger(name):
    """Get a logger with the specified name."""
    return logging.getLogger(name)
