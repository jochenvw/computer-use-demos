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

from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from . import progress
from .config import Settings

TITLE = "EU HEALTHCARE COMPUTER-USE AGENT"
SUBTITLE = "Any app · any file · any database  ->  FHIR · OMOP · your schema"

# kind -> (badge, badge style, text style)
STYLES = {
    "start": ("[REQUEST]", "bold white on dark_blue", "bold white"),
    "step": ("[STEP]", "bold cyan", "cyan"),
    "query": ("[SQL]", "bold yellow", "yellow"),
    "thinking": ("[THINKING]", "bold magenta", "italic plum2"),
    "agent": ("[AGENT]", "bold bright_white", "bright_white"),
    "result": ("[RESULT]", "bold green", "green"),
    "done": ("[DONE]", "bold black on green", "bold green"),
    "warn": ("[NOTE]", "bold dark_orange", "dark_orange"),
    "error": ("[ERROR]", "bold white on red", "bold red"),
    "info": ("[INFO]", "bold dodger_blue1", "dodger_blue1"),
}
BADGE_WIDTH = 11


def hospital_art() -> Text:
    """A hospital with a red cross; only glyphs present in Consolas/Lucida."""
    inner = 36
    total = inner + 2
    art = Text()

    def centered(width: int) -> str:
        return " " * ((total - width) // 2)

    for width in (8, 8, 22, 22, 8, 8):
        art.append("  " + centered(width))
        art.append("█" * width + "\n", style="bold red")
    art.append("  " + "▄" * total + "\n", style="grey85")
    sign = " + CLINICAL DATA AGENT + "
    left = (inner - len(sign)) // 2
    art.append("  █", style="grey85")
    art.append(" " * left)
    art.append(sign, style="bold white on red")
    art.append(" " * (inner - left - len(sign)))
    art.append("█\n", style="grey85")
    windows = "  ▓▓ " * 7 + " "
    for _ in range(2):
        art.append("  █", style="grey85")
        art.append(windows, style="bright_cyan")
        art.append("█\n", style="grey85")
    for door in ("▐▀▀▀▀▌", "▐    ▌"):
        art.append("  █", style="grey85")
        art.append(windows[:15], style="bright_cyan")
        art.append(door, style="yellow")
        art.append(windows[21:], style="bright_cyan")
        art.append("█\n", style="grey85")
    art.append("  " + "▀" * total + "\n", style="grey85")
    art.append("═" * (total + 4), style="grey42")
    return art


def _info_lines(settings: Settings, port: int) -> Table:
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="grey62", no_wrap=True)
    grid.add_column(style="white")
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
    console.print(hospital_art())
    console.print(Text(f"  {TITLE}", style="bold white"))
    console.print(Text(f"  {SUBTITLE}\n", style="grey62"))
    console.print(Panel(
        Group(_info_lines(settings, port), Text(), _legend(), Text("Stop: Ctrl+C", style="grey50")),
        title="Clinical data retrieval demo", border_style="red",
    ))


def render_line(stamp: str, kind: str | None, level: int, message: str) -> Table:
    row = Table.grid(padding=(0, 1))
    row.add_column(width=8, no_wrap=True)
    row.add_column(width=BADGE_WIDTH, no_wrap=True)
    row.add_column(ratio=1, overflow="fold")
    if kind in STYLES:
        badge, badge_style, text_style = STYLES[kind]
    elif level >= logging.ERROR:
        badge, badge_style, text_style = "[ERROR]", "bold red", "red"
    elif level >= logging.WARNING:
        badge, badge_style, text_style = "[WARN]", "dark_orange", "dark_orange"
    else:
        badge, badge_style, text_style = "log", "grey42", "grey46"
    row.add_row(Text(stamp, style="grey50"), Text(badge, style=badge_style), Text(message, style=text_style))
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
        chosen: list[Table] = []
        used = 0
        for stamp, kind, level, message in reversed(list(self.feed.lines)):
            lines = max(len(Text(message).wrap(console, text_width)), 1)
            if used + lines > height:
                break
            used += lines
            chosen.append(render_line(stamp, kind, level, message))
        chosen.reverse()
        body: object = Group(*chosen) if chosen else Text(
            "Waiting for a request from the test UI…", style="grey50"
        )
        yield Panel(body, title="Agent activity", title_align="left",
                    border_style="grey37", height=height + 2)


class Header:
    def __init__(self, settings: Settings, port: int) -> None:
        self.art = hospital_art()
        self.info = _info_lines(settings, port)
        self.spinner = Spinner("line", style="bold yellow")

    def status(self) -> object:
        state = progress.current()
        if not state.get("job"):
            return Text.assemble(("● ", "bold green"), ("Idle – waiting for a request", "green"))
        self.spinner.text = Text(
            f" Working · {state['label']} · {state['elapsed']:.0f} s", style="bold yellow"
        )
        return self.spinner

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        right = Group(
            Text(TITLE, style="bold white"),
            Text(SUBTITLE, style="grey62"),
            Text(),
            self.info,
            Text(),
            self.status(),
            Text(),
            _legend(),
        )
        grid = Table.grid(padding=(0, 3))
        grid.add_column(no_wrap=True)
        grid.add_column(ratio=1)
        grid.add_row(self.art, right)
        yield grid


def run_tui(console: Console, settings: Settings, port: int, serve) -> None:
    feed = Feed()
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[feed], force=True)
    layout = Layout()
    layout.split_column(
        Layout(Header(settings, port), name="header", size=hospital_art().plain.count("\n") + 2),
        Layout(FeedView(feed), name="body"),
    )
    with Live(layout, console=console, screen=True, refresh_per_second=8,
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
