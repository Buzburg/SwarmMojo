#!/usr/bin/env python3
"""
ROMS Unified CLI & MCP Entrypoint
Usage:
  python roms.py mcp                  # Launch full ROMS + Prefrontal FastMCP server
  python roms.py remember --key K ... # Run Prefrontal Cortex CLI subcommands
"""

import sys
from app.prefrontal_cortex import main as prefrontal_main


def run_entry():
    if len(sys.argv) > 1 and sys.argv[1] == "mcp":
        from app.server import start_server
        start_server()
    else:
        raise SystemExit(prefrontal_main(sys.argv[1:]))


if __name__ == "__main__":
    run_entry()
