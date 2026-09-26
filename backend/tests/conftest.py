"""pytest 公共夹具：把后端目录挂上 sys.path，并在每个用例前重置内存仓库。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.store import store  # noqa: E402


@pytest.fixture(autouse=True)
def reset_store():
    """每个用例都面对同一份种子数据，批量流转互不影响。"""
    store.__init__()
    yield
