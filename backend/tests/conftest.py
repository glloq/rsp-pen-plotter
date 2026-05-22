import io

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def two_color_png() -> bytes:
    """A 40x40 PNG: red square on a white background."""
    arr = np.full((40, 40, 3), 255, np.uint8)
    arr[10:30, 10:30] = (220, 20, 20)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()
