"""Pytest configuration and fixtures for dashboard tests."""

import pytest
import respx


@pytest.fixture
def respx_mock():
    """Fixture that provides a respx mock router.

    Configuration:
        - assert_all_mocked=False: Allows unmocked requests to pass through.
          Prevents failures from background HTTP calls (e.g., Reflex init).
        - assert_all_called=True: Ensures every mock defined is actually used.
          Catches typos in mock URLs and dead mocks.
    """
    with respx.mock(assert_all_mocked=False, assert_all_called=True) as mock:
        yield mock
