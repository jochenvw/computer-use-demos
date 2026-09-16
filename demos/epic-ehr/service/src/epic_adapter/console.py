from __future__ import annotations

import argparse
import logging
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

from .config import Settings

CROSS = r"""
        ++++++++
        ++++++++
  ++++++++++++++++++++
  ++++++++++++++++++++
        ++++++++
        ++++++++
"""


def show_banner(console: Console, settings: Settings, port: int) -> None:
    console.print(Text(CROSS, style="bold red"))
    console.print(Text("  EPIC RETRIEVAL AGENT", style="bold white"))
    console.print(Text("  Local files / browser worker / clinical data API\n", style="dim"))
    console.print(Panel(
        Text(
            f"Backend   {settings.backend}\n"
            f"Model     {settings.model_deployment}\n"
            f"API       http://127.0.0.1:{port}\n"
            f"Files     {len(settings.file_roots)} approved root(s)\n"
            "Access    Bearer token required; loopback only\n"
            "Stop      Ctrl+C\n\n"
            "Use synthetic data. Browser actions require an authorized read-only account.\n"
            "No patient details, screenshots, or model reasoning are printed.",
        ),
        title="Clinical data retrieval demo", border_style="red",
    ))


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
    console = Console()
    show_banner(console, settings, args.port)
    if args.banner_only:
        return
    if not settings.bearer_token or settings.bearer_token.startswith("replace-"):
        parser.error("Set API_BEARER_TOKEN to a generated secret before starting the API.")
    if args.tunnel:
        run_with_tunnel(console, args.port)
        return
    logging.basicConfig(
        level=logging.INFO, format="%(message)s",
        handlers=[RichHandler(console=console, markup=False, show_path=False)],
    )
    # SDK HTTP logs may contain endpoint details. Keep only explicit, sanitized events.
    for name in ("httpx", "httpcore", "openai", "azure"):
        logging.getLogger(name).setLevel(logging.WARNING)
    import uvicorn
    uvicorn.run(
        "epic_adapter.api:app", host="127.0.0.1", port=args.port,
        workers=1, access_log=False, log_config=None,
    )


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
