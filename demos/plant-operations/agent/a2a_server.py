"""
A2A-compliant HTTP server for the SRE Operational Reliability Agent.

Exposes:
  GET  /.well-known/agent.json   — A2A agent card (discovery)
  POST /                         — JSON-RPC endpoint (tasks/send, etc.)

Usage:
    uv run python a2a_server.py [--host 127.0.0.1] [--port 10100]
"""

import argparse
import sys

import uvicorn

from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager

import config
from agent_card import build_agent_card
from a2a_handler import SREAgentExecutor


def build_app(host: str = "localhost", port: int = 10100):
    """Construct the A2A Starlette ASGI application."""
    agent_card = build_agent_card(host=host, port=port)

    executor = SREAgentExecutor()
    task_store = InMemoryTaskStore()
    queue_manager = InMemoryQueueManager()

    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        queue_manager=queue_manager,
    )

    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    return a2a_app


def main():
    parser = argparse.ArgumentParser(description="A2A server for the SRE agent")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=10100, help="Port (default: 10100)")
    args = parser.parse_args()

    config.validate()

    print()
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  SRE AGENT — A2A SERVER                                     ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print()
    print(f"  Agent card:  http://{args.host}:{args.port}/.well-known/agent.json")
    print(f"  JSON-RPC:    http://{args.host}:{args.port}/")
    print()
    config.print_config()
    print()

    a2a_app = build_app(host=args.host, port=args.port)

    uvicorn.run(a2a_app.build(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
