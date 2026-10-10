import itertools
import os
import shutil
from pathlib import Path

import pytest

_counter = itertools.count()


def scratch_root() -> Path:
    """Scratch space for tests that need real files on disk.

    Defaults to `.pytest_tmp` beside the repo rather than the OS temp directory,
    which is not always writable (e.g. the Windows sandbox this project is often
    developed in). Override with BLOGC_TEST_TMP when running elsewhere.
    """
    root = Path(
        os.environ.get("BLOGC_TEST_TMP")
        or Path(__file__).resolve().parent.parent / ".pytest_tmp"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def work_dir():
    """A fresh, uniquely named directory under scratch_root().

    Deliberately built with mkdir() instead of tempfile.mkdtemp(): mkdtemp()
    requests mode 0o700, which yields a locked-down directory that a restricted
    sandbox token cannot write into.
    """
    path = scratch_root() / f"case_{os.getpid()}_{next(_counter)}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
