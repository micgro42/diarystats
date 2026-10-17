import shutil
from pathlib import Path

import pytest

from diarystats.config import load

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def lifelog(tmp_path: Path) -> Path:
    """A copy of the fixture archive, safe to change."""
    target = tmp_path / "lifelog"
    shutil.copytree(FIXTURES / "lifelog", target)
    return target


@pytest.fixture
def cfg(tmp_path: Path, lifelog: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        f'archive_dir = "{lifelog}"\n'
        "[links]\n"
        'garmin = "https://connect.garmin.com/modern/sleep/{date}"\n'
        "[sink]\n"
        f'dir = "{tmp_path / "rendered"}"\n'
    )
    return load(path)
