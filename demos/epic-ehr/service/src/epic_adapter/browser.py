"""Screenshot-only control of one explicitly allowlisted browser tab."""

from __future__ import annotations

import base64
from urllib.parse import urlsplit

from .config import Settings


def origin_of(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        return ""
    port = parsed.port
    suffix = f":{port}" if port and port != (443 if parsed.scheme == "https" else 80) else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{suffix}"


class BrowserSession:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._playwright = None
        self._page = None
        self._popup_opened = False

    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            browser = self._playwright.chromium.connect_over_cdp(
                self.settings.browser_cdp_url, timeout=10_000
            )
            matches = [
                page for context in browser.contexts for page in context.pages
                if origin_of(page.url) == origin_of(self.settings.epic_origin)
            ]
            if len(matches) != 1:
                raise RuntimeError("Open exactly one tab on the configured Epic origin.")
            self._page = matches[0]
            self._page.set_default_timeout(10_000)
            self._page.route("**/*", self._guard_navigation)
            self._page.on("dialog", self._dismiss_dialog)
            self._page.on("popup", self._close_popup)
            self._page.bring_to_front()
            return self
        except Exception:
            self._playwright.stop()
            self._playwright = None
            raise

    @staticmethod
    def _dismiss_dialog(dialog) -> None:
        dialog.dismiss()

    def _close_popup(self, page) -> None:
        self._popup_opened = True
        page.close()

    def _guard_navigation(self, route) -> None:
        if (route.request.is_navigation_request()
                and origin_of(route.request.url) != origin_of(self.settings.epic_origin)):
            route.abort()
        else:
            route.continue_()

    def _check(self) -> None:
        if self._popup_opened:
            raise RuntimeError("A new browser window was requested; this workflow is not supported.")
        if (self._page is None or self._page.is_closed()
                or origin_of(self._page.url) != origin_of(self.settings.epic_origin)):
            raise RuntimeError("The approved Epic tab is unavailable or left its allowed origin.")
        if self.settings.browser_window_title:
            if self._page.title() != self.settings.browser_window_title:
                raise RuntimeError("The Epic tab title no longer matches the configured title.")

    def screenshot(self) -> str:
        self._check()
        image = self._page.screenshot(type="jpeg", quality=55, full_page=False, scale="css")
        if len(image) > 2_000_000:
            raise RuntimeError("Browser screenshot exceeds the configured transport limit.")
        return "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")

    def _point(self, values: dict) -> tuple[int, int]:
        # Screenshot coordinates are native viewport pixels, not desktop coordinates.
        size = self._page.evaluate("({width: innerWidth, height: innerHeight})")
        x, y = values["x"], values["y"]
        if (isinstance(x, bool) or isinstance(y, bool)
                or not isinstance(x, int) or not isinstance(y, int)
                or not 0 <= x < size["width"] or not 0 <= y < size["height"]):
            raise ValueError("Action coordinates are outside the browser viewport.")
        return x, y

    def execute(self, name: str, values: dict) -> None:
        self._check()
        if name == "click":
            x, y = self._point(values)
            self._page.evaluate(
                """({x, y}) => {
                    const previous = document.getElementById("epic-demo-click-marker");
                    if (previous) previous.remove();
                    const marker = document.createElement("div");
                    marker.id = "epic-demo-click-marker";
                    Object.assign(marker.style, {
                        position: "fixed", left: `${x - 15}px`, top: `${y - 15}px`,
                        width: "30px", height: "30px", border: "4px solid #ff1744",
                        borderRadius: "50%", boxSizing: "border-box",
                        background: "rgba(255, 23, 68, 0.18)",
                        pointerEvents: "none", zIndex: "2147483647",
                        boxShadow: "0 0 0 3px rgba(255,255,255,.9)",
                    });
                    document.documentElement.appendChild(marker);
                    setTimeout(() => marker.remove(), 1200);
                }""",
                {"x": x, "y": y},
            )
            self._page.mouse.click(x, y)
        elif name == "type_text":
            text = values["text"]
            if not isinstance(text, str) or not 1 <= len(text) <= 256:
                raise ValueError("Text input must contain between 1 and 256 characters.")
            self._page.keyboard.insert_text(text)
        elif name == "press_key":
            key = values["key"]
            if key not in {"Enter", "Tab", "Escape", "Backspace", "ArrowDown", "ArrowUp"}:
                raise ValueError("Keyboard shortcut is not permitted.")
            self._page.keyboard.press(key)
        elif name == "scroll":
            delta = values["delta_y"]
            if isinstance(delta, bool) or not isinstance(delta, int) or abs(delta) > 1000:
                raise ValueError("Scroll distance is outside the permitted range.")
            self._page.mouse.wheel(0, delta)
        elif name != "observe":
            raise ValueError("Unknown browser action.")
        self._page.wait_for_timeout(500)
        self._check()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if self._page is not None and not self._page.is_closed():
                self._page.unroute_all(behavior="wait")
                self._page.remove_listener("dialog", self._dismiss_dialog)
                self._page.remove_listener("popup", self._close_popup)
        finally:
            # Disconnect the controller; leave the operator's logged-in browser running.
            if self._playwright is not None:
                self._playwright.stop()
