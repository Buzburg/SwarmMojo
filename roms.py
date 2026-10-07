#!/usr/bin/env python3
"""
Compatibility entry point for SwarmMojo; existing ROMS commands remain available.
Usage:
  python roms.py harness --request examples/harness-request.json
  python roms.py mcp                  # Launch the configured MCP server
  python roms.py remember --key K ... # Run a local tool
"""

import sys
from app.prefrontal_cortex import main as prefrontal_main


def run_entry():
    if len(sys.argv) > 1 and sys.argv[1] == "harness":
        from app.harness_cli import main
        raise SystemExit(main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "correction":
        from app.corrections_cli import main
        raise SystemExit(main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "mcp":
        from app.server import start_server
        start_server()
    else:
        raise SystemExit(prefrontal_main(sys.argv[1:]))


if __name__ == "__main__":
    run_entry()
