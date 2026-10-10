"""Command-Line Interface for SwarmMojo MetaHarness."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from app.meta.harness import MetaHarness
from app.meta.builder import AgentBuilder, EnvironmentBuilder, TeamBuilder


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="swarmmojo meta",
        description="SwarmMojo MetaHarness: Multi-Agent & Multi-Model Orchestration Engine",
    )
    subparsers = parser.add_subparsers(dest="command")

    # list-agents
    subparsers.add_parser("list-agents", help="List all registered premade and custom agents")

    # list-teams
    subparsers.add_parser("list-teams", help="List all multi-agent team topologies")

    # list-envs
    subparsers.add_parser("list-envs", help="List all registered execution environments")

    # list-models
    subparsers.add_parser("list-models", help="List available local and remote model profiles")

    # run
    run_p = subparsers.add_parser("run", help="Execute a task across a multi-agent team")
    run_p.add_argument("--task", required=True, help="Task or objective description")
    run_p.add_argument("--team", default="fullstack_team", help="Team ID to execute task")
    run_p.add_argument("--env", default="default", help="Environment ID for execution sandbox")
    run_p.add_argument("--model", help="Global model override (e.g. ollama-qwen-coder, mock)")
    run_p.add_argument("--json", action="store_true", help="Output full JSON report")

    # create-agent
    ca_p = subparsers.add_parser("create-agent", help="Create and save a custom agent manifest")
    ca_p.add_argument("--id", required=True, help="Unique agent identifier")
    ca_p.add_argument("--name", required=True, help="Display name")
    ca_p.add_argument("--role", required=True, help="Role description")
    ca_p.add_argument("--division", default="engineering", help="Agent division")
    ca_p.add_argument("--model", default="mock", help="Model profile name")
    ca_p.add_argument("--tools", default="", help="Comma-separated tool names")
    ca_p.add_argument("--prompt", default="", help="Core system instructions")

    # create-env
    ce_p = subparsers.add_parser("create-env", help="Create and save a custom execution sandbox")
    ce_p.add_argument("--id", required=True, help="Unique environment identifier")
    ce_p.add_argument("--name", required=True, help="Display name")
    ce_p.add_argument("--root", default=".", help="Workspace root path")
    ce_p.add_argument("--no-snapshots", action="store_true", help="Disable Rewind snapshots")
    ce_p.add_argument("--no-breaker", action="store_true", help="Disable Horizon circuit breaker")

    args = parser.parse_args(argv)
    harness = MetaHarness()

    if args.command == "list-agents":
        agents = harness.list_agents()
        print(f"\nRegistered Agents ({len(agents)} total):")
        for a in agents:
            print(f" - [{a['id']}] {a['name']} ({a['role']})")
            print(f"     Division: {a['division']} | Model: {a['model_profile']} | Memory: {a['memory_policy']}")
        return 0

    elif args.command == "list-teams":
        teams = harness.list_teams()
        print(f"\nRegistered Multi-Agent Teams ({len(teams)} total):")
        for t in teams:
            members_str = ", ".join(t["member_ids"])
            print(f" - [{t['id']}] {t['name']} (Mode: {t['mode']})")
            print(f"     Coordinator: {t['coordinator_id']} | Members: {members_str}")
            print(f"     Description: {t['description']}")
        return 0

    elif args.command == "list-envs":
        envs = harness.list_environments()
        print(f"\nExecution Environments ({len(envs)} total):")
        for e in envs:
            print(f" - [{e['id']}] {e['name']} (Root: {e['root_path']})")
            print(f"     Snapshots: {e['snapshot_on_action']} | Breaker: {e['circuit_breaker_enabled']} | PathCarry: {e['path_audit_enabled']}")
        return 0

    elif args.command == "list-models":
        models = harness.list_models()
        print(f"\nModel Profiles ({len(models)} total):")
        for name, cfg in models.items():
            print(f" - [{name}] Model: {cfg['model_id']} | Backend: {cfg['backend']} | URL: {cfg['base_url']}")
        return 0

    elif args.command == "run":
        overrides = {"all": args.model} if args.model else {}
        report = harness.run_task(
            task=args.task,
            team_id=args.team,
            env_id=args.env,
            model_overrides=overrides,
        )
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"\n=======================================================")
            print(f"SwarmMojo MetaHarness Execution: {report['team_name']}")
            print(f"Task: {report['task']}")
            print(f"Latency: {report['total_latency_ms']} ms | Mode: {report['mode']}")
            print(f"Participating Agents: {len(report['participating_agents'])}")
            for pa in report["participating_agents"]:
                print(f"  * {pa['name']} ({pa['role']}) -> Model: {pa['model']} [{pa['backend']}]")
            print(f"\n--- Coordinator Synthesis & Proposal ---")
            print(report["synthesis"])
            print(f"\n[Status: Bounded proposal prepared. Operator approval required: {report['approval_required']}]")
            print(f"=======================================================\n")
        return 0

    elif args.command == "create-agent":
        tools_list = [t.strip() for t in args.tools.split(",") if t.strip()]
        builder = (
            AgentBuilder(args.id)
            .name(args.name)
            .role(args.role)
            .division(args.division)
            .model_profile(args.model)
            .tools(tools_list)
            .system_prompt(args.prompt)
        )
        saved_path = builder.save()
        print(f"[+] Successfully saved custom agent manifest to: {saved_path}")
        return 0

    elif args.command == "create-env":
        builder = (
            EnvironmentBuilder(args.id)
            .name(args.name)
            .root_path(args.root)
            .snapshot_on_action(not args.no_snapshots)
            .circuit_breaker_enabled(not args.no_breaker)
        )
        saved_path = builder.save()
        print(f"[+] Successfully saved execution environment to: {saved_path}")
        return 0

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
