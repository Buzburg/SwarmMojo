"""Command line and JSON status interface."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .config import config_path, load, state_home
from .engine import Harness, validate_decision
from .inference import SGLang, make_backend
from .memory import Memory
from .planner import local_plan
from .serving import doctor, launch_plan, serve
from .tools import Tools, validate_action


def parser():
    p = argparse.ArgumentParser(prog="swarm-mojo", description="Swarm Mojo: grounded reviews, workflow rehearsal, and approved actions")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--config", type=Path)
    p.add_argument("--state-dir", type=Path, default=state_home())
    commands = p.add_subparsers(dest="command", required=True)
    ui = commands.add_parser('ui', help='Open the local persistent assistant server')
    ui.add_argument('--workspace', type=Path, default=Path.cwd())
    ui.add_argument('--port', type=int, default=7878)
    ui.add_argument('--offline', action='store_true')
    ui.add_argument('--open-browser', action='store_true')
    commands.add_parser("init", help="Create user configuration without overwriting")
    commands.add_parser("models", help="Show profiles and weight-only memory estimates")
    commands.add_parser("doctor", help="Check local Omarchy and ROCm runtime")
    plan = commands.add_parser("plan", help="Show an exact local plan without executing")
    plan.add_argument("goal")
    plan.add_argument('--workspace', type=Path, default=Path.cwd())
    run = commands.add_parser("run", help="Run or resume a bounded agent task")
    run.add_argument("goal", nargs="?")
    run.add_argument("--workspace", type=Path, default=Path.cwd())
    run.add_argument("--model")
    run.add_argument("--resume")
    run.add_argument("--approve", help="Approve only the exact pending action ticket")
    run.add_argument("--offline", action="store_true", help="Disable all model/network decisions")
    run.add_argument("--allow-write", action="store_true", help="Allow scoped workspace writes for this run")
    run.add_argument("--interactive", action="store_true", help="Ask before individual mutations or commands")
    run.add_argument("--json", action="store_true")
    run.add_argument('--verify-command', action='append', help='Authorize a completion check as a JSON argv array (up to three)')
    run.add_argument('--requirements', type=Path, help='User-authored JSON tree of deterministic completion checks')
    run.add_argument('--workflow', help='Reviewed workflow ID')
    chat = commands.add_parser('chat', help='Send a message in a persistent conversation')
    chat.add_argument('message')
    chat.add_argument('--conversation')
    chat.add_argument('--workspace', type=Path, default=Path.cwd())
    chat.add_argument('--offline', action='store_true')
    conversations = commands.add_parser('conversations', help='List conversations or their source history')
    conversations.add_argument('--conversation')
    conversations.add_argument('--query', help='Search current revisions in the selected conversation')
    conversations.add_argument('--workspace', type=Path, default=Path.cwd())
    note = commands.add_parser('remember', help='Add an explicit note or correction to a conversation')
    note.add_argument('conversation')
    note.add_argument('text')
    note.add_argument('--correct', type=int)
    note.add_argument('--workspace', type=Path, default=Path.cwd())
    workflow = commands.add_parser('workflow', help='Propose, test, compare, review, or list workflows')
    workflow.add_argument('operation', choices=['list', 'propose', 'learn', 'test', 'compare', 'approve'])
    workflow.add_argument('--file', type=Path)
    workflow.add_argument('--id')
    workflow.add_argument('--baseline', help='Baseline workflow ID for compare')
    workflow.add_argument('--source-session')
    workflow.add_argument('--name')
    workflow.add_argument('--workspace', type=Path, default=Path.cwd())
    inputs = commands.add_parser('workflow-input', help='Collect validated workflow inputs without a model')
    inputs.add_argument('operation', choices=['list', 'start', 'show', 'set', 'cancel', 'prepare'])
    inputs.add_argument('--id', help='Input draft ID')
    inputs.add_argument('--file', type=Path, help='Template for start; input values for set (JSON)')
    inputs.add_argument('--workspace', type=Path, default=Path.cwd())
    check = commands.add_parser('check', help='Evaluate a requirements tree without executing commands or calling a model')
    check.add_argument('file', type=Path)
    check.add_argument('--workspace', type=Path, default=Path.cwd())
    rehearsal = commands.add_parser('rehearse', help='Check proposed automation changes with TriggerTangle; never approve or execute them')
    rehearsal.add_argument('--baseline', type=Path, required=True)
    rehearsal.add_argument('--candidate', type=Path, required=True)
    rehearsal.add_argument('--suite', type=Path, required=True)
    rehearsal.add_argument('--node', help='Operator-selected Node executable')
    rehearsal.add_argument('--max-states', type=int, default=256)
    rehearsal.add_argument('--max-transitions', type=int, default=2048)
    mapping = commands.add_parser('repo-map', help='Map observed Python symbols and imports without executing code')
    mapping.add_argument('--workspace', type=Path, default=Path.cwd())
    mapping.add_argument('--path', default='.')
    swarm = commands.add_parser('swarm-review', help='Prepare specialist review packets; --model explicitly enables model reviews')
    swarm.add_argument('goal')
    swarm.add_argument('--workspace', type=Path, default=Path.cwd())
    swarm.add_argument('--path', default='.')
    swarm.add_argument('--mode', type=str.lower, choices=['low', 'medium', 'high', 'max'], default='low')
    swarm.add_argument('--model', help='Explicit configured model profile; omitted means no model calls')
    swarm.add_argument('--timeout', type=int, default=30)
    swarm.add_argument('--max-tokens', type=int, default=1024)
    for name in ('index', 'recall', 'forget-index'):
        command = commands.add_parser(name, help='Manage or search the local source-evidence index')
        command.add_argument('--workspace', type=Path, default=Path.cwd())
        if name == 'index':
            command.add_argument('--path', default='.')
        if name == 'recall':
            command.add_argument('query')
    audit = commands.add_parser('audit', help='Inspect observations, model interpretations, and their provenance')
    audit.add_argument('session')
    for name in ('search', 'review', 'claim'):
        command = commands.add_parser(name, help='Bounded local evidence tools with optional semantic judgments')
        command.add_argument('--workspace', type=Path, default=Path.cwd())
        command.add_argument('--path', default='.')
        command.add_argument('--semantic', action='store_true')
        command.add_argument('--model')
        if name == 'search':
            command.add_argument('query')
        if name == 'claim':
            command.add_argument('claim')
            command.add_argument('--quote', required=True)
    judge = commands.add_parser('judge', help='Evaluate typed questions from a JSON state/questions document')
    judge.add_argument('file', type=Path)
    judge.add_argument('--model')
    calibration = commands.add_parser('calibrate', help='Evaluate routing abstention and label-order sensitivity on a live server')
    calibration.add_argument('--fixtures', type=Path)
    calibration.add_argument('--output', type=Path, required=True)
    calibration.add_argument('--model')
    choices = commands.add_parser('evaluate-choices', help='Measure held-out menu accuracy, calibration, and shuffled-context control')
    choices.add_argument('file', type=Path, help='Jevlike-shaped JSONL: context, options, zero-based label, optional group')
    choices.add_argument('--output', type=Path, required=True)
    choices.add_argument('--model')
    mcp = commands.add_parser('mcp', help='Serve read-only judgment and evidence tools over MCP stdio')
    mcp.add_argument('--workspace', type=Path, default=Path.cwd())
    mcp.add_argument('--model')
    mcp.add_argument('--offline', action='store_true')
    mcp.add_argument('--max-decisions', type=int, default=240, help='Generation budget for this MCP process (1..10000)')
    mcp.add_argument('--rehearsal-baseline', type=Path, help='Operator baseline outside the agent workspace; enables rehearsal with --rehearsal-suite')
    mcp.add_argument('--rehearsal-suite', type=Path, help='Operator acceptance cases outside the agent workspace')
    mcp.add_argument('--rehearsal-node', help='Operator-selected Node executable for rehearsal')
    listen = commands.add_parser('listen', help='Accept finalized transcript JSONL on stdin; no audio recording')
    listen.add_argument('--workspace', type=Path, default=Path.cwd())
    listen.add_argument('--model')
    listen.add_argument('--offline', action='store_true')
    status = commands.add_parser("status", help="Read session status and audit events")
    status.add_argument("session", nargs="?")
    status.add_argument("--events", action="store_true")
    recipe = commands.add_parser("recipe", help="Save an exact user-authored goal-to-tools workflow")
    recipe.add_argument("goal")
    recipe.add_argument("file", type=Path, help="JSON array of typed tool actions")
    recipe.add_argument("--workspace", type=Path, default=Path.cwd())
    start = commands.add_parser("serve", help="Start one SGLang model in the foreground")
    start.add_argument("model", nargs="?", default="qwen27")
    start.add_argument("--dry-run", action="store_true")
    probe = commands.add_parser("probe", help="Verify a running model's full decision protocol")
    probe.add_argument("model", nargs="?", default="qwen27")
    tmt = commands.add_parser("tmt-train", help="Train the optional TMT research port on an explicit UTF-8 file")
    tmt.add_argument("file", type=Path)
    tmt.add_argument("--checkpoint", type=Path, required=True)
    tmt.add_argument("--steps", type=int, default=256)
    return p


def show(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def read_requirements(path):
    from .requirements import validate
    if path.stat().st_size > 64000:
        raise ValueError('Requirements exceed 64 KB')
    return validate(json.loads(path.read_text(encoding='utf-8')))


def main(argv=None):
    args = parser().parse_args(argv)
    memory = None
    try:
        if args.command == 'repo-map':
            from .swarm import repo_map
            show(repo_map(args.workspace, args.path))
            return 0
        if args.command == 'swarm-review':
            from .swarm import review
            profile = None
            if args.model:
                model_config = load(args.config)
                if args.model not in model_config['models']:
                    raise ValueError('Unknown model profile')
                profile = model_config['models'][args.model]
            report = review(args.workspace, args.goal, path=args.path, mode=args.mode,
                            profile=profile, timeout=args.timeout, max_tokens=args.max_tokens)
            show(report)
            return 0 if report['status'] in {'prepared', 'review-required'} else 2
        if args.command == "init":
            destination = args.config or config_path()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8") as handle:
                handle.write(Path(__file__).with_name("defaults.toml").read_text(encoding="utf-8"))
            print(f"Created {destination}")
            return 0
        if args.command == 'rehearse':
            from .rehearsal import rehearse
            report = rehearse(args.baseline, args.candidate, args.suite, node=args.node,
                              max_states=args.max_states, max_transitions=args.max_transitions)
            show(report)
            return 0 if report['status'] == 'review-required' else 2
        config = load(args.config)
        if args.command == 'ui':
            from .web import serve as serve_ui
            serve_ui(config, args.state_dir, args.workspace, args.port, args.offline, args.open_browser)
        elif args.command in {'chat', 'conversations', 'remember'}:
            from .conversations import Conversations, chat
            memory = Memory(args.state_dir)
            store = Conversations(memory, args.workspace)
            if args.command == 'chat':
                cid = args.conversation or store.create(args.message[:100] or 'Conversation')
                show({'conversation': cid, 'result': chat(config, memory, args.workspace, cid, args.message, args.offline)})
            elif args.command == 'remember':
                show({'entry': store.append(args.conversation, 'correction' if args.correct is not None else 'note', args.text, replaces=args.correct)})
            else:
                if args.query is not None:
                    if not args.conversation:
                        raise ValueError('--query requires --conversation')
                    show(store.search(args.conversation, args.query))
                else:
                    show(store.entries(args.conversation) if args.conversation else store.list())
        elif args.command == 'workflow-input':
            from .workflow_inputs import WorkflowInputs
            memory = Memory(args.state_dir)
            store = WorkflowInputs(memory, args.workspace)
            if args.operation == 'list':
                show(store.list())
            elif args.operation in {'start', 'set'}:
                if not args.file or args.file.stat().st_size > 64000:
                    raise ValueError('A JSON --file of at most 64 KB is required')
                value = json.loads(args.file.read_text(encoding='utf-8'))
                show(store.start(value) if args.operation == 'start' else store.set(args.id, value))
            elif args.operation == 'show':
                show(store.get(args.id))
            elif args.operation == 'cancel':
                show(store.cancel(args.id))
            else:
                show(store.prepare(args.id))
        elif args.command == 'workflow':
            from .workflows import Workflows
            memory = Memory(args.state_dir)
            store = Workflows(memory, args.workspace)
            if args.operation == 'list':
                show(store.list())
            elif args.operation == 'learn':
                show(store.learn(args.source_session, args.name))
            elif args.operation == 'approve':
                show(store.review(args.id))
            else:
                if not args.file or args.file.stat().st_size > 128000:
                    raise ValueError('A bounded JSON --file is required')
                value = json.loads(args.file.read_text(encoding='utf-8'))
                if args.operation == 'propose':
                    show(store.propose(value, args.source_session))
                else:
                    report = (store.compare(args.id, args.baseline, value, config) if args.operation == 'compare'
                              else store.regress(args.id, value, config))
                    show(report)
                    return 0 if report['ok'] else 2
        elif args.command == 'check':
            from .requirements import evaluate
            result = evaluate(read_requirements(args.file), Tools(args.workspace))
            show(result)
            return 0 if result['ok'] else 2
        elif args.command in {'index', 'recall', 'forget-index'}:
            from .knowledge import Knowledge
            memory = Memory(args.state_dir)
            knowledge = Knowledge(memory.db, Tools(args.workspace))
            if args.command == 'index':
                show(knowledge.index(args.path))
            elif args.command == 'recall':
                show(knowledge.search(args.query))
            else:
                show(knowledge.clear())
        elif args.command == 'listen':
            from .transcripts import TranscriptBridge, serve as serve_transcripts
            memory = Memory(args.state_dir)
            bridge = TranscriptBridge(config, memory, args.workspace, args.model, args.offline)
            serve_transcripts(bridge, sys.stdin.buffer, sys.stdout)
        elif args.command == 'mcp':
            from .mcp import serve as serve_mcp
            serve_mcp(args.workspace, None, sys.stdin.buffer, sys.stdout,
                      rehearsal_baseline=args.rehearsal_baseline, rehearsal_suite=args.rehearsal_suite,
                      rehearsal_node=args.rehearsal_node)
        elif args.command == 'evaluate-choices':
            from .choice_eval import read_rows, evaluate
            rows = read_rows(args.file)
            report = {"status": "deprecated", "message": "Decision Maker AI removed pending upgrade"}
            args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
            show(report)
        elif args.command in {'search', 'review', 'claim', 'judge', 'calibrate'}:
            from . import evidence
            scorer = None
            if args.command in {'search', 'review', 'claim'}:
                tools = Tools(args.workspace)
                if args.command == 'search':
                    result = evidence.search(tools, args.query, args.path, scorer)
                elif args.command == 'review':
                    result = evidence.review(tools, args.path, scorer)
                else:
                    result = evidence.verify_claim(tools, args.path, args.claim, args.quote, scorer)
            else:
                result = {"status": "deprecated", "message": "Decision Maker AI removed pending upgrade"}
            show({'result': result, 'decision_calls': 0})
        elif args.command == "models":
            show([launch_plan(config, name) for name in config["models"]])
        elif args.command == "doctor":
            show(doctor())
        elif args.command == "plan":
            from .planner import preview
            memory = Memory(args.state_dir)
            show(preview(config, memory, args.workspace, args.goal))
        elif args.command == "serve":
            result = serve(config, args.model, args.dry_run)
            if isinstance(result, int):
                return result
            show(result)
        elif args.command == "probe":
            settings = config["harness"]
            client = make_backend(config["models"][args.model], settings["timeout_seconds"], settings["max_output_tokens"])
            decision, usage = client.decide("Reply with exactly AEON_READY as your answer, no actions, done true.", [], [])
            validate_decision(decision)
            if decision != {"actions": [], "answer": "AEON_READY", "done": True}:
                raise ValueError("Probe failed: model did not follow the decision protocol")
            show({"ok": True, "model": args.model, "usage": usage})
        elif args.command == "tmt-train":
            from .tmt import train_file
            show(train_file(args.file, args.checkpoint, args.steps))
        else:
            memory = Memory(args.state_dir)
            if args.command == 'audit':
                from .audit import report
                show(report(memory, args.session))
            elif args.command == "recipe":
                if args.file.stat().st_size > 128000:
                    raise ValueError("Recipe exceeds 128 KB")
                actions = json.loads(args.file.read_text(encoding="utf-8"))
                if not isinstance(actions, list) or not 1 <= len(actions) <= config["harness"]["max_steps"]:
                    raise ValueError("Recipe must contain 1..max_steps actions")
                for action in actions:
                    validate_action(action)
                memory.learn_recipe(args.goal, args.workspace, actions, config["harness"]["recipe_ttl_seconds"])
                show({"saved": args.goal, "actions": len(actions), "expires_in_seconds": config["harness"]["recipe_ttl_seconds"]})
            elif args.command == "status":
                if args.session:
                    result = memory.session(args.session)
                    if args.events:
                        result["events"] = memory.events(args.session)
                else:
                    result = [dict(row) for row in memory.db.execute(
                        "SELECT id,goal,status,llm_calls,decision_calls,steps FROM sessions ORDER BY rowid DESC LIMIT 20")]
                show(result)
            else:
                if args.resume and args.goal:
                    raise ValueError("Resume uses the stored goal; omit the new goal")
                def confirm(action, binding):
                    print("Proposed action (run_command has your user account's permissions):", file=sys.stderr)
                    print(json.dumps({"action": action, "observed_target": binding}, indent=2), file=sys.stderr)
                    return input("Execute this exact action? [y/N] ").strip().lower() == "y"
                engine = Harness(config, memory, args.workspace, args.model)
                from .workflows import Workflows
                workflow = Workflows(memory, args.workspace).approved(args.workflow) if args.workflow else None
                result = engine.run(args.goal, args.resume, args.approve, args.offline, args.allow_write,
                                    confirm if args.interactive and sys.stdin.isatty() else None,
                                    [json.loads(value) for value in args.verify_command] if args.verify_command else None,
                                    read_requirements(args.requirements) if args.requirements else None,
                                    workflow=workflow)
                if args.json:
                    show(result)
                else:
                    print(f"{result['status']}: {result['answer']}")
                    print(f"Session {result['session']} | model calls {result['llm_calls']} | judgments {result['decision_calls']} | tool steps {result['tool_steps']}")
                    for event in result["results"]:
                        print(f"\n{event['action']['tool']}:")
                        show(event["result"])
                    if result["pending"]:
                        show(result["pending"])
                    if result['verification_checks']:
                        show(result['verification_checks'])
                return 0 if result["status"] == "complete" else 2
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, ImportError) as exc:
        print(f"swarm-mojo: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Use status to inspect the last recorded action.", file=sys.stderr)
        return 130
    finally:
        if memory:
            memory.close()
