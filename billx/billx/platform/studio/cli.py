"""`billx studio --workspace <name or path> --port 8750`: the confirmation studio, served on
127.0.0.1 only (section 3.1: the team reaches it over Tailscale, never a public bind)."""

import logging

import uvicorn

from billx.platform.studio.app import create_app
from billx.platform.studio.workspace import Workspace, resolve_workspace

HOST = "127.0.0.1"


def run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    workspace = Workspace(resolve_workspace(args.workspace))
    print(f"billx studio: workspace {workspace.root}")
    print(f"open http://{HOST}:{args.port}/")
    uvicorn.run(create_app(workspace), host=HOST, port=args.port, log_level="info")
    return 0
