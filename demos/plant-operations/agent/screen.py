"""Screen capture utilities for the SRE agent."""

import base64
import io

import pyautogui
from PIL import Image

from config import DISPLAY_HEIGHT, DISPLAY_WIDTH, TARGET_WINDOW_TITLE

# Target size for the model (1024x768 is the recommended CUA resolution)
_MODEL_WIDTH = 1024
_MODEL_HEIGHT = 768

# Hard cap: Azure gateway rejects URIs over ~65KB
_MAX_URI_LEN = 60_000

# Window title to capture (substring match)
def _find_window():
    """Find the Plant Manager window and return its bounding box."""
    try:
        import pygetwindow as gw
        windows = [
            window for window in gw.getWindowsWithTitle(TARGET_WINDOW_TITLE)
            if window.title == TARGET_WINDOW_TITLE
        ]
        if windows:
            win = windows[0]
            if win.isMinimized:
                win.restore()
            try:
                win.activate()
            except Exception:
                pass
            return win.left, win.top, win.width, win.height
    except Exception:
        pass
    return None


def _encode(image: Image.Image) -> str:
    """Encode image as a JPEG data URI, reducing quality until it fits the cap."""
    for quality in (40, 25, 15, 10):
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        uri = f"data:image/jpeg;base64,{b64}"
        if len(uri) <= _MAX_URI_LEN:
            return uri
    # Last resort: shrink resolution
    small = image.resize((_MODEL_WIDTH // 2, _MODEL_HEIGHT // 2), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=30)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def capture() -> tuple[str, Image.Image]:
    """Capture the Plant Manager window and return (data_uri, PIL.Image).

    Captures only the expected WPF simulator window.
    """
    try:
        region = _find_window()
        if region:
            x, y, w, h = region
            x, y = max(x, 0), max(y, 0)
            screenshot = pyautogui.screenshot(region=(x, y, w, h))
        else:
            raise RuntimeError(
                f'Expected simulator window "{TARGET_WINDOW_TITLE}" was not found. '
                "Full-screen capture is disabled."
            )
    except Exception as exc:
        raise RuntimeError(f"Screenshot capture failed: {exc}") from exc

    # Resize to model dimensions
    if screenshot.size != (_MODEL_WIDTH, _MODEL_HEIGHT):
        screenshot = screenshot.resize(
            (_MODEL_WIDTH, _MODEL_HEIGHT), Image.LANCZOS
        )

    return _encode(screenshot), screenshot
