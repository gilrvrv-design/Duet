import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import native_device
from helpers import ROOT


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def device():
    """The firmware as a Linux process: its serial link, device API and web app."""
    running = native_device.start()
    try:
        yield running
    finally:
        running.stop()


@pytest.fixture(scope="session")
def browser():
    """Chromium; DUET_CHROMIUM picks an installed one instead of Playwright's own."""
    with sync_playwright() as p:
        launched = p.chromium.launch(executable_path=os.environ.get("DUET_CHROMIUM"))
        yield launched
        launched.close()


@pytest.fixture
def page(browser, device):
    """The device's web app, with its clock under the test's control: it polls only
    when told (page.clock.run_for)."""
    opened = browser.new_page(viewport={"width": 390, "height": 760})
    opened.clock.install()
    yield opened
    opened.close()
