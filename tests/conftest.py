# SPDX-FileCopyrightText: 2026 Xavier Douville
# SPDX-License-Identifier: GPL-3.0-or-later

"""Fixtures for Midea Dehumidifier (Cloud) tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from custom_components."""
    yield
