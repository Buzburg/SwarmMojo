"""Exact intent parsing, HTN methods, and bounded cost-based GOAP search.

No fuzzy match is allowed to become an action. Unknown language escalates.
"""

from dataclasses import dataclass
import heapq
import itertools
import re


@dataclass(frozen=True)
class Operator:
    name: str
    requires: frozenset[str]
    adds: frozenset[str]
    cost: int = 1


def goap(initial, goal, operators, max_expansions=128):
    counter = itertools.count()
    queue = [(0, next(counter), frozenset(initial), [])]
    best = {frozenset(initial): 0}
    for _ in range(max_expansions):
        if not queue:
            return None
        cost, _, state, plan = heapq.heappop(queue)
        if set(goal) <= state:
            return plan
        if cost != best[state]:
            continue
        for op in operators:
            if op.cost < 0:
                raise ValueError("Negative planning cost")
            if op.requires <= state:
                new = state | op.adds
                new_cost = cost + op.cost
                if new_cost < best.get(new, float("inf")):
                    best[new] = new_cost
                    heapq.heappush(queue, (new_cost, next(counter), new, plan + [op.name]))
    return None


def action(tool, **args):
    return {"tool": tool, "args": args}


def _single_plan(goal):
    text = goal.strip()
    normalized = text.lower().rstrip(".!?")
    methods = {
        "inspect project": ("project", [action("list_files", path="."), action("git_status")]),
        "inspect this project": ("project", [action("list_files", path="."), action("git_status")]),
        "git status": ("git", [action("git_status")]),
        "desktop status": ("desktop", [action("desktop_state")]),
        "list windows": ("desktop", [action("desktop_state")]),
        "system status": ("system", [action("system_info")]),
        "list files": ("files", [action("list_files", path=".")]),
    }
    if normalized in methods:
        intent, steps = methods[normalized]
        # HTN decomposes the intent; GOAP orders its prerequisite facts.
        operators = [Operator(str(i), frozenset({f"step{i}"}) if i else frozenset(),
                              frozenset({f"step{i+1}"})) for i in range(len(steps))]
        plan = goap(set(), {f"step{len(steps)}"}, operators)
        return intent, [steps[int(i)] for i in plan]
    match = re.fullmatch(r'read file "([^"\r\n]+)"', text, re.I)
    if match:
        return "read", [action("read_file", path=match[1])]
    match = re.fullmatch(r'read lines (\d{1,7})-(\d{1,7}) of "([^"\r\n]+)"', text, re.I)
    if match:
        from .tools import validate_action
        step = action('read_lines', path=match[3], start_line=int(match[1]), end_line=int(match[2]))
        validate_action(step)
        return 'read_lines', [step]
    match = re.fullmatch(r'find "([^"\r\n]+)" in "([^"\r\n]+)"', text, re.I)
    if match:
        return "search", [action("search", text=match[1], path=match[2])]
    match = re.fullmatch(r'focus window "([^"\r\n]+)"', text, re.I)
    if match:
        return "focus", [action("desktop_state"), action("focus_window", title=match[1])]
    match = re.fullmatch(r'recall "([^"\r\n]+)"', text, re.I)
    if match:
        return 'recall', [action('recall', query=match[1])]
    return None


def local_plan(goal):
    """Compile exact read-only sequences; never execute a recognized prefix."""
    direct = _single_plan(goal)
    if direct:
        return direct
    # Quoted paths and search strings may themselves contain separators.
    parts, start, quoted, index = [], 0, False, 0
    while index < len(goal):
        if goal[index] == '"':
            quoted = not quoted
        if not quoted:
            separator = re.match(r';|\r?\n|\s+then\s+', goal[index:], re.I)
            if separator:
                parts.append(goal[start:index].strip())
                index += len(separator[0]); start = index
                continue
        index += 1
    parts.append(goal[start:].strip())
    if quoted or not 2 <= len(parts) <= 8 or any(not part for part in parts):
        return None
    from .tools import READ_TOOLS
    actions = []
    for part in parts:
        plan = _single_plan(part)
        if not plan or any(a['tool'] not in READ_TOOLS for a in plan[1]):
            return None
        for step in plan[1]:
            if step not in actions:
                actions.append(step)
    return 'sequence', actions


def resolve_local(memory, workspace, goal, workflow=None):
    """Shared planning contract for preview and execution; no model or actions."""
    if not isinstance(goal, str) or not 1 <= len(goal.encode()) <= 16000:
        raise ValueError('Goal must contain 1..16000 UTF-8 bytes')
    source = 'workflow'
    if workflow is None:
        requested = re.fullmatch(r'run workflow "([a-z0-9_-]{1,64})"', goal.strip())
        if requested:
            from .workflows import Workflows
            workflow = Workflows(memory, workspace).named(requested[1])
            source = 'reviewed_workflow'
    if workflow is not None:
        from .workflows import validate
        validate(workflow)
        return {'source': source, 'intent': None,
                'actions': [s['action'] for s in workflow['steps']], 'workflow': workflow}
    known = local_plan(goal)
    if known:
        return {'source': 'local', 'intent': known[0], 'actions': known[1], 'workflow': None}
    recipe = memory.recipe(goal, workspace)
    if recipe:
        return {'source': 'exact_recipe', 'intent': 'recipe', 'actions': recipe, 'workflow': None}
    return {'source': 'model_required', 'intent': None, 'actions': [], 'workflow': None}


def preview(config, memory, workspace, goal):
    from .tools import Tools, READ_TOOLS
    tools = Tools(workspace)
    plan = resolve_local(memory, tools.root, goal)
    return {**plan, 'workspace': str(tools.root), 'goal': goal,
            'tool_steps': len(plan['actions']),
            'within_step_budget': len(plan['actions']) <= config['harness']['max_steps'],
            'requires_approval': any(a['tool'] not in READ_TOOLS for a in plan['actions']),
            'note': 'Preview only. No tools or models executed. Conditions and approval are checked at execution.'}
