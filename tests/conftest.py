from pathlib import Path

import pytest

from helpers import ROOT


@pytest.fixture
def root() -> Path:
    return ROOT
