import io
import os
import tempfile

# Isolate the job-history database from the real one before pen_plotter imports.
os.environ.setdefault("OMNIPLOT_DB", os.path.join(tempfile.gettempdir(), "omniplot_test.db"))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from pen_plotter.converters.defaults import register_default_converters  # noqa: E402
from pen_plotter.converters.registry import registry  # noqa: E402
from pen_plotter.persistence import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _app_setup() -> None:
    """Prime the converter registry and database, mirroring the app lifespan."""
    register_default_converters(registry)
    init_db()


@pytest.fixture
def two_color_png() -> bytes:
    """A 40x40 PNG: red square on a white background."""
    arr = np.full((40, 40, 3), 255, np.uint8)
    arr[10:30, 10:30] = (220, 20, 20)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()
