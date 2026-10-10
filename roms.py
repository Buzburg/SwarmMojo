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
    elif len(sys.argv) > 1 and sys.argv[1] == "drift":
        import json
        from app.engines.drift import MojoDrift
        drift = MojoDrift()
        goal = sys.argv[2] if len(sys.argv) > 2 else "execute task safely"
        action = sys.argv[3] if len(sys.argv) > 3 else "running command"
        res = drift.evaluate_action(goal, action)
        print(json.dumps(res, indent=2))
        raise SystemExit(0 if res.get("status") != "blocked" else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "statefresh":
        import json
        from app.engines.statefresh import StateFreshCoordinator
        coord = StateFreshCoordinator()
        target = sys.argv[2] if len(sys.argv) > 2 else "sample.txt"
        lease = coord.acquire_lease(target, holder="cli")
        print(json.dumps({"lease_acquired": lease is not None, "path": target}, indent=2))
        raise SystemExit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "workflowproof":
        import json
        from app.engines.workflowproof import WorkflowProofEngine
        engine = WorkflowProofEngine()
        status = engine.verify_proofs()
        print(json.dumps(status, indent=2))
        raise SystemExit(0 if status.get("valid", True) else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "cortex":
        import json
        from app.engines.cortex import CortexEngine
        cortex = CortexEngine()
        action = sys.argv[2] if len(sys.argv) > 2 else "run tests"
        status = cortex.evaluate_hazard(action)
        print(json.dumps(status, indent=2))
        raise SystemExit(0 if not status.get("hazard") else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "triad":
        import json
        from app.engines.triad import TriadEngine
        engine = TriadEngine()
        summary = engine.summary()
        print(json.dumps(summary, indent=2))
        raise SystemExit(0)
    elif len(sys.argv) > 1 and sys.argv[1] in ("mojo-memory", "mojomemory"):
        import json
        from app.engines.mojo_memory import MojoMemory
        mem = MojoMemory()
        stats = mem.stats()
        print(json.dumps(stats, indent=2))
        raise SystemExit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "studio":
        import json
        from app.engines.studio import StudioAgentEngine
        studio = StudioAgentEngine()
        subcmd = sys.argv[2] if len(sys.argv) > 2 else "prompt"
        if subcmd == "prompt":
            subject = sys.argv[3] if len(sys.argv) > 3 else "Cinematic cyberpunk cityscape in rain"
            res = studio.generate_shot_prompt(subject=subject)
            print(json.dumps(res, indent=2))
        elif subcmd == "comfyui":
            prompt = sys.argv[3] if len(sys.argv) > 3 else "Cinematic scene"
            res = studio.export_comfyui_workflow(prompt=prompt)
            print(json.dumps(res, indent=2))
        elif subcmd == "banner":
            headline = sys.argv[3] if len(sys.argv) > 3 else "Next-Gen AI Agent Platform"
            subtext = sys.argv[4] if len(sys.argv) > 4 else "Autonomous Multimodal Execution"
            res = studio.craft_banner_spec(platform="website_hero", headline=headline, subtext=subtext)
            print(json.dumps(res, indent=2))
        elif subcmd == "status":
            res = studio.comfy.check_status()
            print(json.dumps(res, indent=2))
        raise SystemExit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "design":
        import json
        from app.engines.design import DesignAgentEngine
        engine = DesignAgentEngine()
        subcmd = sys.argv[2] if len(sys.argv) > 2 else "landing"
        if subcmd == "landing":
            proj = sys.argv[3] if len(sys.argv) > 3 else "SwarmMojo"
            head = sys.argv[4] if len(sys.argv) > 4 else "Autonomous Multi-Agent AI Harness"
            subhead = sys.argv[5] if len(sys.argv) > 5 else "Sub-microsecond Mojo acceleration with Impeccable UI craft"
            res = engine.build_landing_page(project_name=proj, headline=head, subheadline=subhead)
            print(json.dumps(res, indent=2))
        elif subcmd == "dashboard":
            title = sys.argv[3] if len(sys.argv) > 3 else "SwarmMojo"
            res = engine.build_admin_dashboard(
                dashboard_title=title,
                stats=[
                    {"label": "Active Agents", "value": "12", "delta": "+20%"},
                    {"label": "Verified DAGs", "value": "1,420", "delta": "+99.9%"},
                    {"label": "Avg Latency", "value": "12µs", "delta": "-85%"},
                ],
                recent_activity=[
                    {"agent": "Atlas", "action": "Task DAG Dispatched", "status": "ok", "time": "2m ago"},
                    {"agent": "Daedalus", "action": "Pi Slice Edit Committed", "status": "ok", "time": "5m ago"},
                    {"agent": "Vitruvius", "action": "UI Landing Page Built", "status": "ok", "time": "12m ago"},
                ],
            )
            print(json.dumps(res, indent=2))
        raise SystemExit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "writer":
        import json
        from app.engines.writer import WriterAgentEngine
        writer = WriterAgentEngine()
        subcmd = sys.argv[2] if len(sys.argv) > 2 else "audit"
        if subcmd == "audit":
            text = sys.argv[3] if len(sys.argv) > 3 else "In today's digital landscape, it is crucial to delve into AI."
            res = writer.audit_prose(text)
            print(json.dumps(res, indent=2))
        elif subcmd == "clean":
            text = sys.argv[3] if len(sys.argv) > 3 else "Furthermore, the bridge stands as a testament to engineering."
            res = writer.clean_prose(text)
            print(json.dumps(res, indent=2))
        elif subcmd == "plan":
            title = sys.argv[3] if len(sys.argv) > 3 else "The Singularity Protocol"
            genre = sys.argv[4] if len(sys.argv) > 4 else "hard sci-fi"
            res = writer.plan_book(
                title=title,
                genre=genre,
                chapters_data=[
                    {"title": "The First Signal", "summary": "Discovery of the anomalous vector stream", "words": 3000},
                    {"title": "Recursive Convergence", "summary": "Autonomous subagents initiate replication", "words": 3500},
                ],
            )
            print(json.dumps(res, indent=2))
        raise SystemExit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "meta":
        from app.meta.cli import main as meta_main
        raise SystemExit(meta_main(sys.argv[2:]))
    else:
        raise SystemExit(prefrontal_main(sys.argv[1:]))


if __name__ == "__main__":
    run_entry()
