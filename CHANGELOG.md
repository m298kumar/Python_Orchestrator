# Changelog
All notable changes to this project will be documented in this file.

## [Unreleased]
### Added
- Rate limiting for API endpoints (100 requests/minute per IP)
- Configurable heuristics for discrepancy detection (YAML config)
- Configurable heuristics for test case generation (YAML config)
- Structured JSON logging configuration
- Docker image vulnerability scanning in CI (Trivy)
- Dependency scanning in CI (bandit, pip-audit)
- Non-root user in Dockerfile

### Changed
- Increased coverage matcher Jaccard threshold from 30% to 50% for better accuracy
- Updated discrepancy detector to load heuristics from config
- Updated scorer to load generic phrases from config
- Updated API routes to use structured logging

### Fixed
- None

## [0.5.0] - 2026-03-28
### Added
- Initial release of STLC Automation Platform