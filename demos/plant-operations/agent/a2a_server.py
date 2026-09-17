"""
A2A-compliant HTTP server for the SRE Operational Reliability Agent.

Exposes:
  GET  /.well-known/agent-card.json — A2A agent card (discovery)
  GET  /.well-known/agent.json      — Legacy discovery alias
  POST /                            — JSON-RPC endpoint (SendMessage, etc.)

Usage:
    uv run --frozen python a2a_server.py [--host 127.0.0.1] [--port 10100]
"""

import argparse
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

import config
from agent_card import build_agent_card
from a2a_handler import SREAgentExecutor


def build_app(host: str = "localhost", port: int = 10100) -> Starlette:
    """Construct the A2A Starlette ASGI application."""
    agent_card = build_agent_card(host=host, port=port)

    executor = SREAgentExecutor()
    task_store = InMemoryTaskStore()
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=task_store,
        agent_card=agent_card,
    )

    @asynccontextmanager
    async def lifespan(app: Starlette):
        try:
            yield
        finally:
            await request_handler.aclose()

    return Starlette(
        routes=[
            *create_agent_card_routes(agent_card),
            *create_agent_card_routes(agent_card, card_url="/.well-known/agent.json"),
            *create_jsonrpc_routes(request_handler, "/", enable_v0_3_compat=True),
        ],
        lifespan=lifespan,
    )


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
    print(f"  Agent card:  http://{args.host}:{args.port}/.well-known/agent-card.json")
    print(f"  JSON-RPC:    http://{args.host}:{args.port}/")
    print()
    config.print_config()
    print()

    a2a_app = build_app(host=args.host, port=args.port)

    uvicorn.run(a2a_app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
