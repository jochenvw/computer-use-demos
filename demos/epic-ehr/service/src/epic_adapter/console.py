from __future__ import annotations

import argparse
import logging
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from urllib.parse import urlsplit
from urllib.request import urlopen

from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import progress
from .config import Settings

TITLE = "HEALTH REWIRED"
EVENT = "MUNICH 2026"
PRODUCT = "CLINICAL DATA AGENT"
SUBTITLE = ("Admitted in Italy, now in the Netherlands  ->  "
            "the Italian hospital record for the Dutch MDT")
BEFORE = "Before: a FHIR / OMOP mapper for every system."
NOW = "Now: portals, scans and databases read as they are, in any output format."

# MDT Observatory dark tokens, mirrored from the tester UI (see design-language.md).
INK = "#dbe7f1"
MUTED = "#8ea6ba"
ACCENT = "#fd8ea1"
SUCCESS = "#4ade80"
WARNING = "#fbbf24"
DANGER = "#f87171"
LINK = "#4da6ff"
CHROME = "#0b1a29"

# kind -> (badge, badge style, text style); plain words a clinician can follow.
STYLES = {
    "start": (" REQUEST ", f"bold {CHROME} on {ACCENT}", f"bold {INK}"),
    "step": (" ACTION ", f"bold {LINK}", INK),
    "query": (" QUERY ", f"bold {WARNING}", WARNING),
    "thinking": (" THINKING ", f"bold {ACCENT}", f"italic {ACCENT}"),
    "agent": (" AGENT ", f"bold {INK}", INK),
    "result": (" FOUND ", f"bold {SUCCESS}", SUCCESS),
    "done": (" DONE ", f"bold {CHROME} on {SUCCESS}", f"bold {SUCCESS}"),
    "warn": (" NOTE ", f"bold {WARNING}", WARNING),
    "error": (" PROBLEM ", f"bold {CHROME} on {DANGER}", f"bold {DANGER}"),
    "info": (" INFO ", f"bold {MUTED}", MUTED),
}
BADGE_WIDTH = 11
FEED_MIN_ROWS = 8

# 5x7 pixel font, rendered with half blocks so each glyph is 5 columns by 4 rows.
_GLYPHS = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": (".###.", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "6": ("..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."),
    " ": ("...",) * 7,
}
_CROSS = ("..###..", "..###..", "#######", "#######", "#######", "..###..", "..###..")


def _half_blocks(rows: tuple[str, ...] | list[str]) -> list[str]:
    rows = list(rows) + ["." * len(rows[0])]
    cells = {("#", "#"): "█", ("#", "."): "▀", (".", "#"): "▄", (".", "."): " "}
    return ["".join(cells[pair] for pair in zip(top, bottom))
            for top, bottom in zip(rows[0::2], rows[1::2])]


def big_text(text: str, style: str) -> Text:
    """Block lettering for the conference title (only glyphs present in Consolas)."""
    glyphs = [_GLYPHS.get(char, _GLYPHS[" "]) for char in text.upper()]
    rows = [".".join(glyph[row] for glyph in glyphs) for row in range(7)]
    return Text("\n".join(_half_blocks(rows)), style=style, no_wrap=True)


def _width(text: Text) -> int:
    return max(len(line) for line in text.plain.splitlines())


def title_block(width: int, height: int | None = None) -> RenderableType:
    """Largest title that fits: one line, two stacked lines, or plain text."""
    cross = Text("\n".join(_half_blocks(_CROSS)), style=f"bold {ACCENT}", no_wrap=True)
    title = big_text(TITLE, f"bold {INK}")
    event = big_text(EVENT, f"bold {ACCENT}")
    gap = 4
    tall_enough = height is None or height >= 26
    options = (
        (True, [title, event]), (False, [title, event]),
        (True, [Group(title, event)]), (False, [Group(title, event)]),
    )
    for with_cross, cells in options:
        stacked = isinstance(cells[0], Group)
        needed = (_width(title) if stacked else _width(title) + gap + _width(event))
        needed += (_width(cross) + gap) if with_cross else 0
        if width < needed or (stacked and not tall_enough):
            continue
        grid = Table.grid(padding=(0, gap))
        row = ([cross] if with_cross else []) + cells
        for _ in row:
            grid.add_column(no_wrap=True)
        grid.add_row(*row)
        return grid
    return Text.assemble(("+ ", f"bold {ACCENT}"), (TITLE, f"bold {INK}"),
                         ("  ·  ", MUTED), (EVENT, f"bold {ACCENT}"))


def _tagline() -> Text:
    return Text.assemble((PRODUCT, f"bold {MUTED}"), ("   ", ""), (SUBTITLE, INK))


def _shift() -> Text:
    return Text.assemble((BEFORE, MUTED), ("   ", ""), (NOW, f"bold {INK}"))


def _info_lines(settings: Settings, port: int) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=MUTED, no_wrap=True)
    grid.add_column(style=INK)
    grid.add_row("Model", settings.model_deployment or "(not configured)")
    grid.add_row("Reasoning", f"{settings.reasoning_effort} effort · "
                 f"{settings.reasoning_summary} thinking summaries")
    grid.add_row("Skills", "epic-browser · local-files · sql-desktop")
    grid.add_row("Outputs", "FHIR R4 · OMOP CDM · HL7 · any schema / ontology")
    grid.add_row("API", f"http://127.0.0.1:{port}  (bearer token, loopback only)")
    return grid


def _legend() -> Text:
    legend = Text()
    for kind in ("step", "query", "thinking", "result"):
        badge, style, _ = STYLES[kind]
        legend.append(badge, style=style)
        legend.append("  ")
    return legend


def show_banner(console: Console, settings: Settings, port: int) -> None:
    console.print(title_block(console.width))
    console.print()
    console.print(_tagline())
    console.print(Panel(
        Group(_info_lines(settings, port), Text(), _legend(), Text("Stop: Ctrl+C", style=MUTED)),
        title=PRODUCT, border_style=ACCENT,
    ))


def render_line(stamp: str, kind: str | None, level: int, message: str) -> Table:
    row = Table.grid(padding=(0, 1))
    row.add_column(width=8, no_wrap=True)
    row.add_column(width=BADGE_WIDTH, no_wrap=True)
    row.add_column(ratio=1, overflow="fold")
    if kind in STYLES:
        badge, badge_style, text_style = STYLES[kind]
    elif level >= logging.ERROR:
        badge, badge_style, text_style = STYLES["error"]
    elif level >= logging.WARNING:
        badge, badge_style, text_style = STYLES["warn"]
    else:
        badge, badge_style, text_style = " log ", MUTED, MUTED
    row.add_row(Text(stamp, style=MUTED), Text(badge, style=badge_style), Text(message, style=text_style))
    return row


class Feed(logging.Handler):
    """Collects log records for the live view (bounded)."""

    def __init__(self, size: int = 1000) -> None:
        super().__init__(logging.INFO)
        self.lines: deque[tuple[str, str | None, int, str]] = deque(maxlen=size)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging
            message = str(record.msg)
        stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
        self.lines.append((stamp, getattr(record, "story", None), record.levelno, message))


class PrintHandler(logging.Handler):
    """Fallback for consoles without VT support: same styling, no fixed header."""

    def __init__(self, console: Console) -> None:
        super().__init__(logging.INFO)
        self.console = console

    def emit(self, record: logging.LogRecord) -> None:
        try:
            stamp = time.strftime("%H:%M:%S", time.localtime(record.created))
            self.console.print(render_line(stamp, getattr(record, "story", None),
                                           record.levelno, record.getMessage()))
        except Exception:  # noqa: BLE001
            self.handleError(record)


class FeedView:
    """Newest log lines that fit the panel; older lines scroll off the top."""

    def __init__(self, feed: Feed) -> None:
        self.feed = feed

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        height = max((options.height or console.height) - 2, 1)
        text_width = max(options.max_width - 4 - 8 - BADGE_WIDTH - 2, 20)
        chosen: list[RenderableType] = []
        used = 0
        for stamp, kind, level, message in reversed(list(self.feed.lines)):
            # A blank line before each new request separates the demo runs.
            lines = max(len(Text(message).wrap(console, text_width)), 1) + (kind == "start")
            if used + lines > height:
                break
            used += lines
            chosen.append(render_line(stamp, kind, level, message))
            if kind == "start":
                chosen.append(Text())
        chosen.reverse()
        body: object = Group(*chosen) if chosen else Text(
            "Waiting for the Dutch MDT's request…  press 1, 2 or 3 on the demo screen.",
            style=MUTED,
        )
        yield Panel(body, title=Text(" WHAT THE AGENT IS DOING ", style=f"bold {MUTED}"),
                    title_align="left", border_style=MUTED, height=height + 2, padding=(0, 1))


def _pipeline(active: str, failed: bool = False) -> Text:
    """ASK -> WATCH -> RECEIVE, the same three acts as the tester's Stage mode."""
    acts = ("ask", "watch", "receive")
    at = acts.index(active)
    line = Text()
    for index, name in enumerate(acts):
        label = f" {index + 1} · {name.upper()} "
        if index == at and failed:
            style = f"bold {CHROME} on {DANGER}"
        elif index == at:
            style = f"bold {CHROME} on {SUCCESS if name == 'receive' else ACCENT}"
        elif index < at:
            style = f"bold {SUCCESS}"
        else:
            style = MUTED
        line.append(label, style=style)
        if index < len(acts) - 1:
            line.append("  ──  ", style=MUTED)
    return line


def status_row() -> Table:
    state = progress.current()
    last = state.get("last")
    if state.get("job"):
        pulse = "●" if int(time.monotonic() * 2) % 2 else "○"
        pipe = _pipeline("watch")
        status = Text.assemble((f"{pulse} Working  ", f"bold {ACCENT}"),
                               (f"{state['label']} · {state['elapsed']:.0f} s", INK))
    elif last and last["kind"] == "done":
        pipe = _pipeline("receive")
        status = Text.assemble(("● Delivered  ", f"bold {SUCCESS}"), (last["text"], INK))
    elif last:
        pipe = _pipeline("watch", failed=True)
        status = Text.assemble(("● Stopped  ", f"bold {DANGER}"), (last["text"], INK))
    else:
        pipe = _pipeline("ask")
        status = Text.assemble(("● Ready  ", f"bold {SUCCESS}"),
                               ("waiting for the Dutch MDT's request", INK))
    row = Table.grid(padding=(0, 4))
    row.add_column(no_wrap=True)
    row.add_column(ratio=1, overflow="fold")
    row.add_row(pipe, status)
    return row


class Header:
    def __init__(self, settings: Settings, port: int) -> None:
        self.settings = settings
        self.port = port

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield title_block(options.max_width, console.height)
        yield Text()
        yield _tagline()
        yield _shift()
        yield Text()
        yield status_row()


class Footer:
    def __init__(self, settings: Settings, port: int) -> None:
        self.text = Text(
            f"{settings.model_deployment or 'model not configured'} · "
            f"{settings.reasoning_effort} reasoning · API 127.0.0.1:{port} · "
            "Ctrl + / Ctrl − zoom · Ctrl+C stop",
            style=MUTED, no_wrap=True, overflow="ellipsis",
        )

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        yield self.text


class Screen:
    """Header sized to its content each frame, so zooming the terminal reflows it."""

    def __init__(self, settings: Settings, port: int, feed: Feed) -> None:
        self.header = Header(settings, port)
        self.footer = Footer(settings, port)
        self.feed = FeedView(feed)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        height = options.height or console.height
        header_rows = len(console.render_lines(self.header, options.update(height=None), pad=False))
        header_rows = min(header_rows, max(height - FEED_MIN_ROWS - 1, 1))
        layout = Layout()
        layout.split_column(
            Layout(self.header, name="header", size=header_rows + 1),
            Layout(self.feed, name="body"),
            Layout(self.footer, name="footer", size=1),
        )
        yield layout


def run_tui(console: Console, settings: Settings, port: int, serve) -> None:
    feed = Feed()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[feed], force=True)
    with Live(Screen(settings, port, feed), console=console, screen=True, refresh_per_second=4,
              redirect_stdout=True, redirect_stderr=True):
        serve()


def tui_supported(console: Console) -> bool:
    return (
        os.environ.get("EPIC_TUI", "1") != "0"
        and console.is_terminal and not console.legacy_windows
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Epic retrieval agent and local API")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--banner-only", action="store_true", help="Preview the terminal banner.")
    parser.add_argument("--tunnel", action="store_true", help="Start the API and an authenticated dev tunnel together.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    settings = Settings.from_env()
    settings.validate()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    console = Console()
    if args.banner_only:
        show_banner(console, settings, args.port)
        return
    if not settings.bearer_token or settings.bearer_token.startswith("replace-"):
        parser.error("Set API_BEARER_TOKEN to a generated secret before starting the API.")
    if args.tunnel:
        show_banner(console, settings, args.port)
        run_with_tunnel(console, args.port)
        return

    def serve() -> None:
        # SDK HTTP logs may contain endpoint details. Keep only explicit, sanitized events.
        for name in ("httpx", "httpcore", "openai", "azure", "copilot"):
            logging.getLogger(name).setLevel(logging.WARNING)
        import uvicorn
        uvicorn.run(
            "epic_adapter.api:app", host="127.0.0.1", port=args.port,
            workers=1, access_log=False, log_config=None,
        )

    if tui_supported(console):
        run_tui(console, settings, args.port, serve)
        return
    show_banner(console, settings, args.port)
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[PrintHandler(console)], force=True)
    serve()


def ensure_port_available(port: int) -> None:
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    except OSError as exc:
        raise RuntimeError(f"Port {port} is already in use; refusing to adopt another API.") from exc


def stop_child(child) -> None:
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def forwarded_tunnel_url(line: str, port: int) -> str | None:
    for match in re.finditer(
        r"https://[a-z0-9.-]+\.devtunnels\.ms(?::443)?(?![a-z0-9.:-])",
        line, re.I,
    ):
        url = match.group(0)
        host = urlsplit(url).hostname
        if host and host.split(".", 1)[0].endswith(f"-{port}"):
            return url
    return None


def run_with_tunnel(console: Console, port: int) -> None:
    """Own both children so a failed tunnel never leaves a public endpoint behind."""
    if not shutil.which("devtunnel"):
        raise RuntimeError("Install the Microsoft dev tunnels CLI and run 'devtunnel user login' first.")
    ensure_port_available(port)
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "epic_adapter.api:app", "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    tunnel = None
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if api.poll() is not None:
                raise RuntimeError("API child exited before health check.")
            try:
                with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError("API health check timed out.")
        tunnel = subprocess.Popen(
            ["devtunnel", "host", "--port-numbers", str(port), "--protocol", "http", "--expiration", "1h"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        console.print("Opening authenticated dev tunnel; waiting for the actual HTTPS URL.")
        lines: queue.Queue[str | None] = queue.Queue(maxsize=64)
        def copy_output():
            for output in iter(tunnel.stdout.readline, ""):
                try:
                    lines.put(output, timeout=.2)
                except queue.Full:
                    pass
            try:
                lines.put(None, timeout=.2)
            except queue.Full:
                pass

        reader = threading.Thread(target=copy_output, daemon=True)
        reader.start()
        printed_url = False
        tunnel_deadline = time.monotonic() + 30
        while True:
            try:
                line = lines.get(timeout=.2)
            except queue.Empty:
                line = ""
            if line is None:
                raise RuntimeError("Dev tunnel exited. Check devtunnel user login and network access.")
            if time.monotonic() >= tunnel_deadline and not printed_url:
                raise RuntimeError("Timed out waiting for devtunnel HTTPS URL. Check devtunnel user login and host access.")
            url = forwarded_tunnel_url(line, port)
            if url and not printed_url:
                console.print(Panel(url, title="API HTTPS URL (copy this)", border_style="green"))
                printed_url = True
            if api.poll() is not None:
                raise RuntimeError("API child exited; closing tunnel.")
            if tunnel.poll() is not None:
                raise RuntimeError("Dev tunnel exited. Check devtunnel user login and network access.")
    finally:
        cleanup_errors = []
        for child in (tunnel, api):
            try:
                stop_child(child)
            except Exception as exc:
                cleanup_errors.append(exc)
        if cleanup_errors and sys.exc_info()[0] is None:
            raise cleanup_errors[0]


if __name__ == "__main__":
    main()
