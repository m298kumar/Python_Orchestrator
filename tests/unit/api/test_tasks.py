"""Focused tests for API pipeline task preparation."""

import pytest
from stlc_platform.api.tasks import _extract_urls_from_requirements


def _config_with_requirement(*urls: str, configured_url: str = "") -> dict:
    config = {
        "requirements": [
            {
                "description": "Registration requirement",
                "acceptance_criteria": [f"Open {url}" for url in urls],
            }
        ],
        "crawler": {},
    }
    if configured_url:
        config["crawler"]["base_url"] = configured_url
    return config


def test_requirement_origin_replaces_stale_crawler_target():
    config = _config_with_requirement(
        "https://demo.opencart.com/index.php?route=account/register",
        configured_url="https://www.demoblaze.com/",
    )

    _extract_urls_from_requirements(config)

    assert config["crawler"]["base_url"] == "https://demo.opencart.com"


def test_matching_configured_origin_is_retained_canonically():
    config = _config_with_requirement(
        "https://demo.opencart.com/index.php?route=account/register",
        configured_url="https://demo.opencart.com/old/path",
    )

    _extract_urls_from_requirements(config)

    assert config["crawler"]["base_url"] == "https://demo.opencart.com"


def test_multiple_origins_require_explicit_matching_target():
    config = _config_with_requirement(
        "https://shop.example.com/register",
        "https://identity.example.net/login",
    )

    with pytest.raises(ValueError, match="multiple application origins"):
        _extract_urls_from_requirements(config)


def test_multiple_origins_accept_explicit_matching_target():
    config = _config_with_requirement(
        "https://shop.example.com/register",
        "https://identity.example.net/login",
        configured_url="https://shop.example.com",
    )

    _extract_urls_from_requirements(config)

    assert config["crawler"]["base_url"] == "https://shop.example.com"
