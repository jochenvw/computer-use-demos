"""Narrow visible Windows desktop control for the approved SSMS demo window."""

from __future__ import annotations

import base64
import ctypes
import io
import os
import signal
import subprocess
import time
from ctypes import wintypes
from pathlib import Path


SW_RESTORE = 9
SW_MAXIMIZE = 3
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP = 0x0002
VK_F5 = 0x74
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _set_clipboard(text: str) -> None:
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    data = text.encode("utf-16-le") + b"\x00\x00"
    for _ in range(10):
        if user32.OpenClipboard(0):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Clipboard is unavailable.")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            raise RuntimeError("Could not place the query on the clipboard.")
    finally:
        user32.CloseClipboard()


def _visible_windows() -> list[tuple[int, str]]:
    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @enum_proc
    def callback(window, _):
        if user32.IsWindowVisible(window):
            length = user32.GetWindowTextLengthW(window)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(window, buffer, len(buffer))
                found.append((int(window), buffer.value))
        return True

    user32.EnumWindows(callback, 0)
    return found


def _title_matches(title: str, names: list[str]) -> bool:
    lowered = title.lower().strip()
    for name in (n.lower() for n in names if n):
        if lowered == name or lowered.endswith("\\" + name):
            return True
        if "." in name:
            stem = name.rsplit(".", 1)[0]
            # Viewers title windows "ecg.jpg - Photos" or, like Paint, "ecg - Paint".
            if name in lowered or lowered.startswith(stem + " - "):
                return True
    return False


def close_windows(names: list[str]) -> int:
    """Politely close the Explorer folder / image viewer windows a skill opened.

    A folder window matches its exact name (or a full path ending in it); a file
    viewer matches when its title contains the file name (with or without extension).
    """
    if not hasattr(ctypes, "windll") or not names:
        return 0
    closed = 0
    for window, title in _visible_windows():
        if _title_matches(title, names):
            ctypes.windll.user32.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE
            closed += 1
    return closed


class WindowsDesktopSession:
    def __init__(self, executable: Path, query_path: Path) -> None:
        if not hasattr(ctypes, "windll"):
            raise RuntimeError("Desktop computer use requires Windows.")
        self.executable = executable
        self.query_path = query_path
        self._user32 = ctypes.windll.user32
        self._window = 0

    def __enter__(self) -> "WindowsDesktopSession":
        if not self.executable.is_file():
            raise RuntimeError("The approved SSMS executable was not found.")
        if not self.query_path.is_file():
            raise RuntimeError("The approved SQL demo query was not found.")
        self._close_existing()
        subprocess.Popen(  # noqa: S603 - fixed executable and arguments
            [
                str(self.executable),
                "-S", "localhost",
                "-E",
                "-d", "OncologiaDemo",
                str(self.query_path),
            ],
            cwd=str(self.query_path.parent),
        )
        self._window = self._wait_for_window()
        # A maximized window keeps the results grid readable in screenshots.
        self._user32.ShowWindow(self._window, SW_MAXIMIZE)
        time.sleep(1)
        self._focus()
        return self

    def _close_existing(self) -> None:
        """Terminate leftover SSMS instances so each demo run starts clean."""
        pids: set[int] = set()
        for window in self._matching_windows():
            pid = wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
            if pid.value and pid.value != os.getpid():
                pids.add(pid.value)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        if pids:
            time.sleep(2)
        self._clear_recovery()

    @staticmethod
    def _clear_recovery() -> None:
        """Drop SSMS auto-recover state so no 'recover files' dialog blocks the demo."""
        home = Path(os.path.expanduser("~"))
        folders = (
            home / "Documents" / "Visual Studio 2017" / "Backup Files",
            home / "AppData" / "Roaming" / "Microsoft" / "SQL Server Management Studio"
            / "20.0_IsoShell" / "AutoRecoverDat",
        )
        for folder in folders:
            if not folder.is_dir():
                continue
            for item in folder.rglob("*"):
                if item.is_file():
                    try:
                        item.unlink()
                    except OSError:
                        pass

    def _wait_for_window(self) -> int:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            window = self._main_window()
            if window:
                left, top, right, bottom = self._rect(window)
                if right - left >= 800 and bottom - top >= 500:
                    time.sleep(3)
                    return self._main_window() or window
            time.sleep(0.5)
        raise RuntimeError("The approved SSMS window did not become visible.")

    def _rect(self, window: int) -> tuple[int, int, int, int]:
        rect = wintypes.RECT()
        if not self._user32.GetWindowRect(window, ctypes.byref(rect)):
            return 0, 0, 0, 0
        return rect.left, rect.top, rect.right, rect.bottom

    def _main_window(self) -> int:
        def area(window: int) -> int:
            left, top, right, bottom = self._rect(window)
            return max(0, right - left) * max(0, bottom - top)

        matches = self._matching_windows()
        return max(matches, key=area) if matches else 0

    def _matching_windows(self) -> list[int]:
        matches: list[int] = []
        enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        @enum_proc
        def callback(window, _):
            if not self._user32.IsWindowVisible(window):
                return True
            length = self._user32.GetWindowTextLengthW(window)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            self._user32.GetWindowTextW(window, buffer, len(buffer))
            title = buffer.value.lower()
            if "sql server management studio" in title:
                matches.append(int(window))
            return True

        self._user32.EnumWindows(callback, 0)
        return matches

    def _focus(self) -> None:
        if not self._window or not self._user32.IsWindow(self._window):
            self._window = self._main_window()
        if not self._window:
            raise RuntimeError("The approved SSMS window is unavailable.")
        if self._user32.IsIconic(self._window):
            self._user32.ShowWindow(self._window, SW_RESTORE)
        self._user32.SetForegroundWindow(self._window)
        time.sleep(0.5)

    def _require_input(self) -> None:
        self._focus()
        if self._user32.GetForegroundWindow() != self._window:
            self._user32.keybd_event(0x12, 0, 0, 0)  # Alt unlocks SetForegroundWindow
            self._user32.keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0)
            self._user32.SetForegroundWindow(self._window)
            time.sleep(0.5)
        if self._user32.GetForegroundWindow() != self._window:
            # Fatal and caller-visible: keystrokes cannot reach a minimized RDP session.
            raise RuntimeError("Skill stopped without verified data: rdp_minimized.")

    def _bounds(self) -> tuple[int, int, int, int]:
        self._focus()
        rect = wintypes.RECT()
        if not self._user32.GetWindowRect(self._window, ctypes.byref(rect)):
            raise RuntimeError("Could not read the approved SSMS window bounds.")
        if rect.right <= rect.left or rect.bottom <= rect.top:
            raise RuntimeError("The approved SSMS window has invalid bounds.")
        return rect.left, rect.top, rect.right, rect.bottom

    def _print_window(self):
        """Capture via PrintWindow; works when the RDP desktop is not being drawn."""
        from PIL import Image

        left, top, right, bottom = self._bounds()
        width, height = right - left, bottom - top
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        for fn in (user32.GetWindowDC, gdi32.CreateCompatibleDC,
                   gdi32.CreateCompatibleBitmap, gdi32.SelectObject):
            fn.restype = ctypes.c_void_p
        user32.GetWindowDC.argtypes = [wintypes.HWND]
        user32.ReleaseDC.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.PrintWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.UINT]
        gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
                                    wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p,
                                    wintypes.UINT]
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        gdi32.DeleteDC.argtypes = [ctypes.c_void_p]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        window_dc = user32.GetWindowDC(self._window)
        if not window_dc:
            return None
        memory_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        try:
            if not memory_dc or not bitmap:
                return None
            gdi32.SelectObject(memory_dc, bitmap)
            if not user32.PrintWindow(self._window, memory_dc, 2):  # PW_RENDERFULLCONTENT
                return None
            header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height,
                                      1, 32, 0, 0, 0, 0, 0, 0)
            buffer = ctypes.create_string_buffer(width * height * 4)
            if not gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer,
                                   ctypes.byref(header), 0):
                return None
            return Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1)
        finally:
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if memory_dc:
                gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(self._window, window_dc)

    def screenshot(self) -> str:
        from PIL import ImageGrab

        image = None
        for attempt in range(2):
            try:
                image = ImageGrab.grab(bbox=self._bounds(), all_screens=True)
                break
            except OSError:
                time.sleep(1 + attempt)
        if image is None:
            image = self._print_window()
        if image is None:
            raise ValueError(
                "Screen capture failed (is the RDP session visible?). Observe again."
            )
        output = io.BytesIO()
        image.convert("RGB").save(output, format="JPEG", quality=65)
        data = output.getvalue()
        if len(data) > 2_000_000:
            raise RuntimeError("Desktop screenshot exceeds the transport limit.")
        return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")

    def click(self, x: int, y: int) -> None:
        left, top, right, bottom = self._bounds()
        if isinstance(x, bool) or isinstance(y, bool):
            raise ValueError("Desktop coordinates must be integers.")
        if not 0 <= x < right - left or not 0 <= y < bottom - top:
            raise ValueError("Desktop coordinates are outside the SSMS window.")
        self._user32.SetCursorPos(left + x, top + y)
        self._user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self._user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        time.sleep(0.5)

    def press_key(self, key: str) -> None:
        self._focus()
        virtual_key = {"F5": VK_F5, "Escape": VK_ESCAPE}.get(key)
        if virtual_key is None:
            raise ValueError("Only F5 and Escape are permitted in SSMS.")
        self._user32.keybd_event(virtual_key, 0, 0, 0)
        self._user32.keybd_event(virtual_key, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(3 if key == "F5" else 0.5)

    def run_query(self, sql: str) -> None:
        """Replace the editor text with an already validated query and execute it."""
        self._require_input()
        _set_clipboard(sql)
        for combo in (VK_A, VK_V):
            self._user32.keybd_event(VK_CONTROL, 0, 0, 0)
            self._user32.keybd_event(combo, 0, 0, 0)
            self._user32.keybd_event(combo, 0, KEYEVENTF_KEYUP, 0)
            self._user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            time.sleep(0.4)
        time.sleep(1)
        self.press_key("F5")

    def scroll(self, delta_y: int) -> None:
        if isinstance(delta_y, bool) or not isinstance(delta_y, int):
            raise ValueError("Scroll distance must be an integer.")
        if not -1000 <= delta_y <= 1000:
            raise ValueError("Scroll distance is outside the permitted range.")
        self._focus()
        self._user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, -delta_y, 0)
        time.sleep(0.5)

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._window = 0
        # Leave the desktop clean for the next scenario (and no save prompt).
        self._close_existing()
