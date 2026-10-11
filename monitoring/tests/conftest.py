"""Shared pytest setup for the Site Signal statistics suite (monitoring/)."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    # Tests that prove a requirement are tagged @pytest.mark.req("REQ-0xx") (validation/requirements.yaml).
    config.addinivalue_line("markers", "req(id): links a test to a requirement in validation/requirements.yaml")
