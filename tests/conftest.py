"""Shared fixtures: load the custom integration in a test Home Assistant."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
