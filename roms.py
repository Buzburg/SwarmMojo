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
    elif len(sys.argv) > 1 and sys.argv[1] == "polyharness":
        from app.polyharness import main as polyharness_main
        raise SystemExit(polyharness_main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] in ("aeon", "swarm", "swarm-mojo"):
        from aeon.cli import main as aeon_main
        raise SystemExit(aeon_main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "symdex":
        from app.engines.symdex import main as symdex_main
        sys.argv = [sys.argv[0] + " symdex", *sys.argv[2:]]
        raise SystemExit(symdex_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "titans":
        from app.engines.titans import main as titans_main
        sys.argv = [sys.argv[0] + " titans", *sys.argv[2:]]
        raise SystemExit(titans_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "toolcall":
        from app.engines.toolcall import main as toolcall_main
        sys.argv = [sys.argv[0] + " toolcall", *sys.argv[2:]]
        raise SystemExit(toolcall_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "sieve":
        from app.engines.sieve import main as sieve_main
        sys.argv = [sys.argv[0] + " sieve", *sys.argv[2:]]
        raise SystemExit(sieve_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "horizon":
        from app.engines.horizon import main as horizon_main
        sys.argv = [sys.argv[0] + " horizon", *sys.argv[2:]]
        raise SystemExit(horizon_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "fastgate":
        from app.engines.fastgate import main as fastgate_main
        sys.argv = [sys.argv[0] + " fastgate", *sys.argv[2:]]
        raise SystemExit(fastgate_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "compact-kv":
        from app.engines.compact_kv import main as compact_kv_main
        sys.argv = [sys.argv[0] + " compact-kv", *sys.argv[2:]]
        raise SystemExit(compact_kv_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "rewind":
        from app.engines.rewind import main as rewind_main
        sys.argv = [sys.argv[0] + " rewind", *sys.argv[2:]]
        raise SystemExit(rewind_main())
    elif len(sys.argv) > 1 and sys.argv[1] == "path-carry":
        import json
        from app.engines.path_carry import audit_directory
        target = sys.argv[2] if len(sys.argv) > 2 else "."
        result = audit_directory(target)
        print(json.dumps(result.to_dict(), indent=2))
        raise SystemExit(0 if result.is_clean else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "meta":
        from app.meta.cli import main as meta_main
        raise SystemExit(meta_main(sys.argv[2:]))
    else:
        raise SystemExit(prefrontal_main(sys.argv[1:]))


if __name__ == "__main__":
    run_entry()
