"""Local-first agent loop with durable approval and execution records."""

import time
import sqlite3

from .inference import InferenceError, SGLang, SYSTEM, jev_choice, make_backend
from .memory import compact, digest, packed
from .planner import local_plan, resolve_local
from .tools import READ_TOOLS, Tools, validate_action
from .recovery import diagnose, redact, repeated_failure
from . import supervisor
from . import requirements as requirement_checks
from .knowledge import Knowledge


def validate_decision(value):
    if not isinstance(value, dict) or set(value) != {"actions", "answer", "done"}:
        raise ValueError("Decision must contain actions, answer, and done")
    if type(value["done"]) is not bool or not isinstance(value["answer"], str) or len(value["answer"])>32000:
        raise ValueError("Invalid decision answer or done flag")
    if not isinstance(value["actions"], list) or len(value["actions"])>8:
        raise ValueError("At most 8 actions per decision")
    for action in value["actions"]:
        validate_action(action)
    if value["done"] and value["actions"]:
        raise ValueError("A decision cannot finish and execute actions simultaneously")
    if not value["done"] and not value["actions"]:
        raise ValueError("Decision made no progress")
    return value


class Harness:
    def __init__(self, config, memory, workspace, model=None, backend=None):
        self.config, self.memory = config, memory
        self.tools = Tools(workspace)
        self.tools.knowledge = Knowledge(memory.db, self.tools)
        self.model = model or config["harness"]["model"]
        if self.model not in config["models"]:
            raise ValueError("Unknown model profile")
        settings = config["harness"]
        self.backend = backend or make_backend(config["models"][self.model], settings["timeout_seconds"], settings["max_output_tokens"])

    def run(self, goal=None, sid=None, approve=None, offline=False, allow_write=False, confirm=None, verify_commands=None, requirements=None, conversation_context=None, workflow=None):
        initial_plan = None
        if not sid:
            initial_plan = resolve_local(self.memory, self.tools.root, goal, workflow)
            workflow = initial_plan['workflow']
        if workflow is not None:
            from .workflows import validate as validate_workflow
            validate_workflow(workflow)
        if conversation_context is not None:
            if not isinstance(conversation_context, dict) or len(packed(conversation_context).encode()) > 12000:
                raise ValueError('Conversation context must be a bounded object')
        if requirements is not None:
            requirement_checks.validate(requirements)
        if verify_commands is not None:
            supervisor.validate_commands(verify_commands)
        if sid:
            session = self.memory.session(sid)
            if session["workspace"] != str(self.tools.root):
                raise ValueError("Resume must use the original workspace")
            goal = session["goal"]
            contexts = [e['context'] for e in self.memory.events(sid) if e['kind'] == 'conversation_context']
            original_context = contexts[0] if contexts else None
            if conversation_context is not None and conversation_context != original_context:
                raise ValueError('Resume must retain the original conversation context')
            conversation_context = original_context
            workflows = [e['plan'] for e in self.memory.events(sid) if e['kind'] == 'workflow_policy']
            original_workflow = workflows[0] if workflows else None
            if workflow is not None and workflow != original_workflow:
                raise ValueError('Resume must retain the original workflow')
            workflow = original_workflow
            stored = [e['commands'] for e in self.memory.events(sid) if e['kind'] == 'verification_policy']
            original = stored[0] if stored else []
            if verify_commands is not None and verify_commands != original:
                raise ValueError('Resume must retain the original verification commands')
            verify_commands = original
            policies = [e['tree'] for e in self.memory.events(sid) if e['kind'] == 'requirements_policy']
            original_tree = policies[0] if policies else None
            if requirements is not None and requirements != original_tree:
                raise ValueError('Resume must retain the original requirements')
            requirements = original_tree
            if session["status"] == "interrupted_action":
                return self.result(sid, "blocked", "Previous action has an uncertain outcome. Inspect its execution_started event before starting another task.")
            if session["status"] == "complete":
                outcomes = [e for e in self.memory.events(sid) if e["kind"] == "outcome"]
                final = outcomes[-1] if outcomes else {"answer": "Session already completed", "verification": "unknown"}
                return self.result(sid, "complete", final["answer"], final["verification"])
        else:
            if not goal or len(goal.encode())>16000:
                raise ValueError("Goal must contain 1..16000 UTF-8 bytes")
            sid = self.memory.new_session(goal, self.tools.root)
            self.memory.event(sid, "goal", {"text": goal})
            verify_commands = verify_commands or []
            self.memory.event(sid, 'verification_policy', {'commands': verify_commands})
            self.memory.event(sid, 'requirements_policy', {'tree': requirements})
            if conversation_context is not None:
                self.memory.event(sid, 'conversation_context', {'context': redact(conversation_context)})
            if workflow is not None:
                self.memory.event(sid, 'workflow_policy', {'plan': workflow})
        settings = self.config["harness"]
        session = self.memory.session(sid)
        calls, steps = session["llm_calls"], session["steps"]
        judge = None
        self.tools.judge = None

        def finish(answer, verification='tool_results'):
            model_reported = verification == 'model_reported'
            checked = None
            if verify_commands:
                # A crash during a user-authorized command must never silently replay it.
                self.memory.update(sid, status='interrupted_action')
                self.memory.event(sid, 'verification_started', {'commands': verify_commands})
                checked = supervisor.check(self.tools.root, verify_commands)
                self.memory.event(sid, 'verification', checked)
            if workflow is not None:
                satisfied = requirement_checks.evaluate(workflow['completion'], self.tools)
                self.memory.event(sid, 'workflow_completion', satisfied)
                if not satisfied['ok']:
                    return self.result(sid, 'needs_verification', 'Workflow completion checks did not pass.', 'workflow_unmet')
                verification = 'workflow_verified'
            if requirements is not None:
                satisfied = requirement_checks.evaluate(requirements, self.tools, checked)
                self.memory.event(sid, 'requirements', redact(satisfied))
                if not satisfied['ok']:
                    return self.result(sid, 'needs_verification', 'Declared requirements have failed or remain unknown; inspect requirement checks.', 'requirements_unmet')
                verification = 'requirements_passed'
            if checked is not None:
                if not checked['ok']:
                    return self.result(sid, 'needs_verification', 'An explicit verification command failed; inspect verification events and repair before starting a new task.', 'failed')
                verification = 'requirements_and_commands_passed' if requirements else 'explicit_checks_passed'
            if judge and model_reported:
                try:
                    observed = [e for e in self.memory.events(sid) if e['kind'] == 'tool']
                    assessment = supervisor.assess(judge, goal, answer, observed)
                    self.memory.event(sid, 'supervisor', {**assessment, 'observed_event_ids': [e['event_id'] for e in observed[-4:]]})
                    if assessment['choice'] == 'incomplete' and assessment['margin'] >= .3:
                        return self.result(sid, 'needs_verification', answer, 'semantic_concern')
                except (RuntimeError, ValueError) as exc:
                    self.memory.event(sid, 'supervisor', {'error': str(exc), 'verification': 'unavailable'})
            return self.result(sid, 'complete', answer, verification)
        pending = session["pending"]
        workflow_index = sum(e['kind'] == 'workflow_step' and e.get('ok') is True for e in self.memory.events(sid))
        actions, local, intent = [], False, None
        if pending:
            if pending.get("state") == "executing":
                self.memory.update(sid, status="interrupted_action")
                return self.result(sid, "blocked", "An action was interrupted; its outcome must be checked manually.")
            actions = [pending["action"]] + pending["remaining"]
            local, intent = pending["local"], pending.get("intent")
        else:
            if approve:
                raise ValueError("No pending action to approve")
            selected = initial_plan or resolve_local(self.memory, self.tools.root, goal, workflow)
            if workflow is not None:
                actions = [s['action'] for s in workflow['steps'][workflow_index:]]
                local, intent = True, None
            elif selected['source'] != 'model_required':
                actions, local, intent = selected['actions'], True, selected['intent']
        if local and steps + len(actions) > settings['max_steps']:
            return self.result(sid, 'budget_exhausted', 'The complete local plan exceeds the remaining tool-step budget; no remaining actions executed.')
        self.memory.update(sid, status="active")
        seen = set()
        mutation_epoch = 0
        successful = []
        retried = set()
        for event in self.memory.events(sid):
            if event["kind"] == "tool":
                seen.add(digest([event["action"], mutation_epoch]))
                if event["result"].get("ok"):
                    successful.append(event["action"])
                    if event["action"]["tool"] not in READ_TOOLS:
                        mutation_epoch += 1
        while True:
            stuck = repeated_failure(self.memory.events(sid))
            if stuck:
                self.memory.event(sid, 'stuck', stuck)
                return self.result(sid, 'blocked', 'Three consecutive identical tool failures; inspect the evidence and change the approach before starting a new task.')
            while actions:
                if steps >= settings["max_steps"]:
                    return self.result(sid, "budget_exhausted", "Tool-step budget reached")
                current, actions = actions[0], actions[1:]
                validate_action(current)
                if workflow is not None:
                    step = workflow['steps'][workflow_index]
                    if current != step['action']:
                        raise ValueError('Pending action does not match workflow step')
                    precondition = requirement_checks.evaluate(step['before'], self.tools)
                    self.memory.event(sid, 'workflow_precondition', {'step': workflow_index, **precondition})
                    if not precondition['ok']:
                        self.memory.update(sid, pending=None)
                        return self.result(sid, 'blocked', 'Workflow precondition did not pass; no action executed.')
                fingerprint = digest([current, mutation_epoch])
                if fingerprint in seen:
                    return self.result(sid, "blocked", "Repeated unchanged action stopped; inspect the previous result")
                try:
                    binding = self.tools.prepare(current)
                except (OSError, ValueError) as exc:
                    self.memory.event(sid, "tool", {"action": current, "result": {"ok": False, "error": str(exc)}})
                    steps += 1
                    self.memory.update(sid, steps=steps, pending=None)
                    seen.add(fingerprint)
                    if local:
                        return self.result(sid, "blocked", str(exc))
                    actions = []
                    break
                ticket = digest([sid, current, binding])[:24]
                mutation = current["tool"] not in READ_TOOLS
                authorized = not mutation or (allow_write and current["tool"] in {"write_file", "edit_file"})
                if approve:
                    if not pending or approve != pending["ticket"] or ticket != pending["ticket"] or binding != pending["binding"]:
                        return self.result(sid, "needs_approval", "Approval does not match the current action and observed target")
                    authorized, approve = True, None
                if mutation and not authorized and confirm:
                    authorized = confirm(current, binding)
                record = {"action": current, "binding": binding, "remaining": actions,
                          "ticket": ticket, "local": local, "intent": intent, "state": "pending"}
                if not authorized:
                    self.memory.update(sid, pending=record)
                    return self.result(sid, "needs_approval", "Review the pending action, then resume with its exact approval ticket")
                # Commit before execution. A crash may never cause an automatic replay.
                record["state"] = "executing"
                self.memory.update(sid, pending=record, status="interrupted_action")
                self.memory.event(sid, "execution_started", {"action": current, "ticket": ticket})
                started = time.monotonic()
                result = redact(self.tools.execute(current, binding))
                if not result.get('ok'):
                    result['diagnosis'] = diagnose(result, judge)
                self.memory.event(sid, "tool", {"action": current, "result": result,
                                              "elapsed_ms": round((time.monotonic()-started)*1000)})
                seen.add(fingerprint)
                steps += 1
                self.memory.update(sid, pending=None, status="active", steps=steps)
                pending = None
                if result.get("ok"):
                    successful.append(current)
                    if mutation:
                        mutation_epoch += 1
                    if workflow is not None:
                        postcondition = requirement_checks.evaluate(step['after'], self.tools)
                        self.memory.event(sid, 'workflow_step', {'step': workflow_index, **postcondition})
                        if not postcondition['ok']:
                            return self.result(sid, 'needs_verification', 'Workflow action ran but its outcome check did not pass.', 'workflow_unmet')
                        workflow_index += 1
                else:
                    if (not mutation and result['diagnosis']['class'] == 'transient'
                            and result['diagnosis']['source'] == 'deterministic' and fingerprint not in retried):
                        retried.add(fingerprint)
                        seen.discard(fingerprint)
                        actions.insert(0, current)
                        self.memory.event(sid, 'recovery', {'action': current, 'policy': 'one read-only retry'})
                        continue
                    if local:
                        return self.result(sid, "blocked", "A local tool failed; see its recorded result")
                    actions = []
                    break
            if local:
                if intent:
                    self.memory.observe(goal, intent)
                # Exact known methods only; classifier guesses never become trusted recipes.
                if workflow is None and local_plan(goal) and all(a["tool"] in READ_TOOLS for a in successful):
                    self.memory.learn_recipe(goal, self.tools.root, successful, settings["recipe_ttl_seconds"])
                return finish('Completed the selected tool plan')
            if offline:
                return self.result(sid, "needs_model", "No exact local plan. Model calls are disabled")
            stuck = repeated_failure(self.memory.events(sid))
            if stuck:
                self.memory.event(sid, 'stuck', stuck)
                return self.result(sid, 'blocked', 'Three consecutive identical tool failures; inspect the evidence and change the approach before starting a new task.')
            if calls >= settings["max_llm_calls"]:
                return self.result(sid, "budget_exhausted", "Language-model call budget reached")
            if steps >= settings["max_steps"]:
                return self.result(sid, "budget_exhausted", "Tool-step budget reached")
            try:
                # Execution markers are audit records, not context; tool/result pairs are atomic.
                events = [e for e in self.memory.events(sid) if e["kind"] == "tool"]
                hints = self.memory.hints(goal)
                if conversation_context is not None:
                    hints.append(conversation_context)
                recalled_event_ids = [e['event_id'] for e in self.memory.events(sid) if e['kind'] == 'conversation_context']
                if self.memory.db.execute('SELECT 1 FROM knowledge_sources WHERE workspace=? LIMIT 1', (str(self.tools.root),)).fetchone():
                    try:
                        recalled = self.tools.knowledge.search(goal[:4000], limit=2)
                        if recalled['matches']:
                            hints.append({'source': 'indexed_files', 'trust': 'untrusted_source_excerpts',
                                          'matches': recalled['matches']})
                            recalled_event_ids.append(self.memory.event(sid, 'recall', {
                                'matches': recalled['matches'], 'trust': recalled['trust']}))
                    except (ValueError, OSError, sqlite3.Error) as exc:
                        self.memory.event(sid, 'recall_error', {'error': str(exc)})
                if self.config.get("tmt", {}).get("checkpoint"):
                    from .tmt import checkpoint_hint
                    hints.append(checkpoint_hint(self.config["tmt"]["checkpoint"], goal,
                                                 self.config["tmt"].get("max_bytes", 512)))
                model_goal = goal if requirements is None else goal+'\n\nUser-defined completion criteria:\n'+packed(requirements)
                budget = settings['max_context_bytes'] - len(SYSTEM.encode()) - len(model_goal.encode()) - len(packed(hints).encode()) - 2048
                context = compact(events, budget)
                calls += 1
                self.memory.update(sid, llm_calls=calls)
                decision, usage = self.backend.decide(model_goal, redact(context), hints)
                validate_decision(decision)
                self.memory.event(sid, "model", {"profile": self.model, "usage": usage, "decision": decision,
                                               'observed_event_ids': [e['event_id'] for e in context]+recalled_event_ids,
                                               'recalled_sources': [{'path': m['path'], 'sha256': m['sha256']} for hint in hints if hint.get('source') == 'indexed_files' for m in hint['matches']]})
                if decision["done"]:
                    # This is model-reported completion, distinct from deterministic verification.
                    return finish(decision['answer'], verification='model_reported')
                actions = decision["actions"]
            except (InferenceError, ValueError, TypeError, KeyError, OSError, ImportError, RuntimeError) as exc:
                self.memory.event(sid, "error", {"error": str(exc)})
                return self.result(sid, "blocked", str(exc))

    def result(self, sid, status, answer, verification="tool_results"):
        self.memory.update(sid, status=status)
        self.memory.event(sid, "outcome", {"status": status, "answer": answer, "verification": verification})
        session = self.memory.session(sid)
        result = {"session": sid, "status": status, "answer": answer, "verification": verification,
                  "llm_calls": session["llm_calls"], "tool_steps": session["steps"], "pending": session["pending"]}
        result['decision_calls'] = session['decision_calls']
        result['verification_checks'] = [e for e in self.memory.events(sid) if e['kind'] in {'verification', 'supervisor', 'requirements', 'workflow_precondition', 'workflow_step', 'workflow_completion'}]
        result["results"] = [e for e in self.memory.events(sid) if e["kind"] == "tool"]
        return result
