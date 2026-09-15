"""
Execute UI actions returned by the computer-use-preview model.

The model returns ResponseComputerToolCall objects whose .action field
is one of: ActionClick, ActionDoubleClick, ActionDrag, ActionKeypress,
ActionMove, ActionScreenshot, ActionScroll, ActionType, ActionWait.

The execute() function accepts the action object (or a dict), dispatches
to the appropriate pyautogui call, and returns a human-readable description.
"""

import time

import pyautogui
import pyperclip

from config import ACTION_DELAY
from screen import _MODEL_WIDTH, _MODEL_HEIGHT, _find_window

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0


def _scale(x: int, y: int) -> tuple[int, int]:
    """Convert model coordinates (1024x768) to absolute screen coordinates.

    The model sees only the WPF window captured at 1024x768.
    We need to map those coordinates back to the window's actual
    position and size on screen.
    """
    region = _find_window()
    if region:
        win_x, win_y, win_w, win_h = region
        win_x, win_y = max(win_x, 0), max(win_y, 0)
        sx = win_w / _MODEL_WIDTH
        sy = win_h / _MODEL_HEIGHT
        return int(win_x + x * sx), int(win_y + y * sy)
    # Fallback: assume full screen
    screen_w, screen_h = pyautogui.size()
    return int(x * screen_w / _MODEL_WIDTH), int(y * screen_h / _MODEL_HEIGHT)

# Key name mapping: model key names → pyautogui key names
_KEY_MAP = {
    "Return": "enter",
    "Enter": "enter",
    "Space": "space",
    "Backspace": "backspace",
    "Tab": "tab",
    "Escape": "escape",
    "ctrl": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "Delete": "delete",
    "Home": "home",
    "End": "end",
    "ArrowUp": "up",
    "ArrowDown": "down",
    "ArrowLeft": "left",
    "ArrowRight": "right",
}


def _to_dict(action) -> dict:
    """Normalize an action object to a dict (handles both SDK objects and dicts)."""
    if isinstance(action, dict):
        return action
    # SDK model object — convert via model_dump or __dict__
    if hasattr(action, "model_dump"):
        return action.model_dump()
    return dict(vars(action))


def _click(a: dict) -> str:
    x, y = _scale(a["x"], a["y"])
    button = a.get("button", "left")
    pyautogui.click(x, y, button=button)
    return f"click({x}, {y}) button={button}"


def _double_click(a: dict) -> str:
    x, y = _scale(a["x"], a["y"])
    pyautogui.doubleClick(x, y)
    return f"double_click({x}, {y})"


def _type_text(a: dict) -> str:
    text = a["text"]
    if text.isascii() and all(c not in text for c in "\t\n"):
        pyautogui.write(text, interval=0.03)
    else:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    preview = text[:40] + ("…" if len(text) > 40 else "")
    return f'type("{preview}")'


def _keypress(a: dict) -> str:
    keys = a.get("keys", [])
    if not keys:
        return "keypress(no keys)"
    mapped = [_KEY_MAP.get(k, k.lower()) for k in keys]
    if len(mapped) > 1:
        pyautogui.hotkey(*mapped)
    else:
        pyautogui.press(mapped[0])
    return f"keypress({'+'.join(keys)})"


def _scroll(a: dict) -> str:
    x, y = _scale(a["x"], a["y"])
    scroll_y = a.get("scroll_y", 0)
    pyautogui.scroll(scroll_y, x=x, y=y)
    return f"scroll({x}, {y}) dy={scroll_y}"


def _move(a: dict) -> str:
    x, y = _scale(a["x"], a["y"])
    pyautogui.moveTo(x, y)
    return f"move({x}, {y})"


def _drag(a: dict) -> str:
    path = a.get("path", [])
    if len(path) < 2:
        return "drag(insufficient path points)"
    start = path[0]
    sx, sy = _scale(start["x"], start["y"])
    pyautogui.moveTo(sx, sy)
    pyautogui.mouseDown()
    try:
        for point in path[1:]:
            px, py = _scale(point["x"], point["y"])
            pyautogui.moveTo(px, py, duration=0.3)
    finally:
        pyautogui.mouseUp()
    return f"drag({len(path)} points)"


def _wait(a: dict) -> str:
    time.sleep(1.0)
    return "wait(1s)"


def _screenshot(a: dict) -> str:
    return "screenshot (caller handles capture)"


_DISPATCH = {
    "click": _click,
    "double_click": _double_click,
    "type": _type_text,
    "keypress": _keypress,
    "scroll": _scroll,
    "move": _move,
    "drag": _drag,
    "wait": _wait,
    "screenshot": _screenshot,
}


def execute(action) -> str:
    """Execute a single UI action and return a description of what was done."""
    a = _to_dict(action)
    action_type = a.get("type", "unknown")
    handler = _DISPATCH.get(action_type)

    if handler is None:
        msg = f"Unknown action type: {action_type}"
        print(f"  ⚠️  {msg}")
        return msg

    detail_keys = [k for k in a if k != "type"]
    details = ", ".join(f"{k}={a[k]}" for k in detail_keys[:4])
    print(f"  ⚡ {action_type}({details})")

    time.sleep(ACTION_DELAY)

    try:
        return handler(a)
    except Exception as exc:
        msg = f"Action {action_type} failed: {exc}"
        print(f"  ❌ {msg}")
        return msg
