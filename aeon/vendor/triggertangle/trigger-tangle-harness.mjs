/*
MIT License

Copyright (c) 2026 Buzburg

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

*/

// src/harness-cli.ts
import { createHash } from "node:crypto";

// src/model.ts
var MAX_TEXT = 2e5;
function record(value, at) {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) throw new Error(`${at} must be an object.`);
  return value;
}
function keys(value, allowed, required, at) {
  for (const key2 of Object.keys(value)) if (!allowed.includes(key2)) throw new Error(`${at}: unsupported property ${JSON.stringify(key2)}.`);
  for (const key2 of required) if (!Object.hasOwn(value, key2)) throw new Error(`${at}.${key2} is required.`);
}
function text(value, at, max = 120) {
  if (typeof value !== "string" || !value.length || value.length > max || /[\u0000-\u001f\u007f]/u.test(value)) throw new Error(`${at} must be nonempty text, at most ${max} characters, without control characters.`);
}
function scalar(value, at) {
  if (value === null || typeof value === "boolean" || typeof value === "number" && Number.isSafeInteger(value) || typeof value === "string" && value.length <= 256) return;
  throw new Error(`${at} must be a string (up to 256 characters), safe integer, boolean or null.`);
}
function list(value, max, at) {
  if (!Array.isArray(value) || value.length > max) throw new Error(`${at} must be an array with at most ${max} items.`);
  return value;
}
function field(value, at, fields) {
  if (typeof value !== "string" || !/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(value) || ["__proto__", "constructor", "prototype"].includes(value)) throw new Error(`${at} is not a supported field name.`);
  fields.add(value);
  if (fields.size > 32) throw new Error("A blueprint may use at most 32 distinct data fields.");
}
function data(value, at, fields) {
  const object2 = record(value, at);
  for (const [key2, item] of Object.entries(object2)) {
    field(key2, at, fields);
    scalar(item, `${at}.${key2}`);
  }
}
function address(value, at) {
  text(value.resource, `${at}.resource`);
  text(value.event, `${at}.event`);
}
function parseBlueprint(text2) {
  if (typeof text2 !== "string" || text2.length > MAX_TEXT) throw new Error("Blueprint text exceeds 200,000 characters.");
  let value;
  try {
    value = JSON.parse(text2);
  } catch {
    throw new Error("Blueprint is not valid JSON. Check commas, quotes and brackets.");
  }
  return validateBlueprint(value);
}
function validateBlueprint(value) {
  const root = record(value, "Blueprint");
  keys(root, ["version", "name", "seed", "workflows"], ["version", "name", "seed", "workflows"], "Blueprint");
  if (root.version !== 1) throw new Error("Only blueprint version 1 is supported.");
  text(root.name, "Blueprint.name", 200);
  const fields = /* @__PURE__ */ new Set();
  const seed = record(root.seed, "seed");
  keys(seed, ["resource", "event", "data"], ["resource", "event", "data"], "seed");
  address(seed, "seed");
  data(seed.data, "seed.data", fields);
  const ids = /* @__PURE__ */ new Set();
  for (const [index, item] of list(root.workflows, 100, "workflows").entries()) {
    const at = `workflows[${index}]`;
    const workflow = record(item, at);
    keys(workflow, ["id", "name", "enabled", "on", "when", "emit"], ["id", "name", "on", "emit"], at);
    text(workflow.id, `${at}.id`, 64);
    text(workflow.name, `${at}.name`, 200);
    if (ids.has(workflow.id)) throw new Error(`Duplicate workflow ID: ${JSON.stringify(workflow.id)}.`);
    ids.add(workflow.id);
    if (Object.hasOwn(workflow, "enabled") && typeof workflow.enabled !== "boolean") throw new Error(`${at}.enabled must be a boolean.`);
    const on = record(workflow.on, `${at}.on`);
    keys(on, ["resource", "event"], ["resource", "event"], `${at}.on`);
    address(on, `${at}.on`);
    if (Object.hasOwn(workflow, "when")) for (const [conditionIndex, item2] of list(workflow.when, 16, `${at}.when`).entries()) {
      const location = `${at}.when[${conditionIndex}]`;
      const condition = record(item2, location);
      if (condition.op === "equals" || condition.op === "notEquals") {
        keys(condition, ["field", "op", "value"], ["field", "op", "value"], location);
        scalar(condition.value, `${location}.value`);
      } else if (condition.op === "exists" || condition.op === "missing") {
        keys(condition, ["field", "op"], ["field", "op"], location);
      } else throw new Error(`${location}.op must be equals, notEquals, exists or missing.`);
      field(condition.field, `${location}.field`, fields);
    }
    for (const [effectIndex, item2] of list(workflow.emit, 16, `${at}.emit`).entries()) {
      const location = `${at}.emit[${effectIndex}]`;
      const effect = record(item2, location);
      keys(effect, ["resource", "event", "set", "unset"], ["resource", "event"], location);
      address(effect, location);
      if (Object.hasOwn(effect, "set")) data(effect.set, `${location}.set`, fields);
      if (Object.hasOwn(effect, "unset")) {
        const unset = list(effect.unset, 32, `${location}.unset`);
        const seen = /* @__PURE__ */ new Set();
        for (const key2 of unset) {
          field(key2, `${location}.unset`, fields);
          if (seen.has(key2)) throw new Error(`${location}.unset repeats a field.`);
          seen.add(key2);
        }
      }
    }
  }
  return value;
}

// src/engine.ts
var DEFAULT_BUDGET = { maxStates: 256, maxTransitions: 2048 };
var NOTES = [
  "Design rehearsal only. No live accounts, tools or workflows were connected or executed.",
  "The result applies only to this seed and these exact, declared resource IDs, event types and field rules.",
  "Delivery is modeled as once per emitted event. Retries, concurrency, timing, changed-only writes, stored records, deduplication and LLM decisions are not modeled.",
  "A cycle is repeatable under this deterministic model, not proof of runaway behavior in a real platform. Settles is not a production safety certification.",
  "Disabling a workflow can break a loop while also removing intended work. Test business outcomes separately."
];
function key(signal) {
  return JSON.stringify([signal.resource, signal.event, Object.entries(signal.data).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)]);
}
function matches(data2, condition) {
  const exists = Object.hasOwn(data2, condition.field);
  switch (condition.op) {
    case "exists":
      return exists;
    case "missing":
      return !exists;
    case "equals":
      return exists && data2[condition.field] === condition.value;
    case "notEquals":
      return !exists || data2[condition.field] !== condition.value;
  }
}
function limits(input) {
  for (const field2 of Object.keys(input)) if (!["maxStates", "maxTransitions"].includes(field2)) throw new Error("Unsupported exploration budget setting.");
  const budget = { ...DEFAULT_BUDGET, ...input };
  if (!Number.isInteger(budget.maxStates) || budget.maxStates < 1 || budget.maxStates > 512 || !Number.isInteger(budget.maxTransitions) || budget.maxTransitions < 1 || budget.maxTransitions > 8192) throw new Error("Budget requires 1\u2013512 states and 1\u20138,192 transitions.");
  return budget;
}
function analyze(input, requestedBudget = {}) {
  const blueprint = validateBlueprint(input);
  const budget = limits(requestedBudget);
  const states = [{ ...blueprint.seed, data: { ...blueprint.seed.data }, id: 0, matches: [] }];
  const transitions = [];
  const identifiers = /* @__PURE__ */ new Map([[key(blueprint.seed), 0]]);
  const parents = [void 0];
  let complete = true;
  exploration: for (let index = 0; index < states.length; index++) {
    const state = states[index];
    for (const workflow of blueprint.workflows) {
      if (workflow.enabled === false || workflow.on.resource !== state.resource || workflow.on.event !== state.event || workflow.when !== void 0 && !workflow.when.every((condition) => matches(state.data, condition))) continue;
      state.matches.push(workflow.id);
      for (const [effectIndex, effect] of workflow.emit.entries()) {
        if (transitions.length >= budget.maxTransitions) {
          complete = false;
          break exploration;
        }
        const data2 = { ...state.data };
        for (const field2 of effect.unset ?? []) delete data2[field2];
        Object.assign(data2, effect.set);
        const signal = { resource: effect.resource, event: effect.event, data: data2 };
        const signature = key(signal);
        let target = identifiers.get(signature);
        if (target === void 0) {
          if (states.length >= budget.maxStates) {
            complete = false;
            break exploration;
          }
          target = states.length;
          identifiers.set(signature, target);
          states.push({ ...signal, id: target, matches: [] });
          parents[target] = { from: index, to: target, workflow: workflow.id, effect: effectIndex };
        }
        transitions.push({ from: index, to: target, workflow: workflow.id, effect: effectIndex });
      }
    }
  }
  const outgoing = states.map(() => []);
  for (const transition of transitions) outgoing[transition.from].push(transition);
  const witness = findCycle(outgoing, parents);
  const status = witness ? "loop-found" : complete ? "settles" : "inconclusive";
  const counts = complete && !witness ? countDeliveries(states, outgoing) : { workflowStarts: null, emittedEvents: null };
  const reason = witness ? `A reachable signal repeats along a causal cycle in this model.${complete ? "" : " Other branches remain unexplored because the budget was reached."}` : complete ? "Every reachable branch settles for this seed under the declared rules." : "The exploration budget was reached before all branches were checked. No conclusion about termination is available.";
  return { schema: "triggertangle.report/v1", name: blueprint.name, blueprint: structuredClone(blueprint), status, complete, reason, budget, stats: { states: states.length, transitions: transitions.length, ...counts }, states, transitions, witness, notes: [...NOTES] };
}
function findCycle(outgoing, parents) {
  const colors = new Uint8Array(outgoing.length);
  const ancestry = [];
  function visit(node) {
    colors[node] = 1;
    for (const edge of outgoing[node]) {
      if (colors[edge.to] === 1) {
        const cycle2 = [edge];
        let current2 = edge.from;
        while (current2 !== edge.to) {
          const parent = ancestry[current2];
          cycle2.unshift(parent);
          current2 = parent.from;
        }
        return cycle2;
      }
      if (colors[edge.to] === 0) {
        ancestry[edge.to] = edge;
        const found = visit(edge.to);
        if (found) return found;
      }
    }
    colors[node] = 2;
    return null;
  }
  const cycle = visit(0);
  if (!cycle) return null;
  const leadIn = [];
  let current = cycle[0].from;
  while (parents[current]) {
    const parent = parents[current];
    leadIn.unshift(parent);
    current = parent.from;
  }
  return { leadIn, cycle };
}
function countDeliveries(states, outgoing) {
  const incoming = new Uint32Array(states.length);
  for (const edges of outgoing) for (const edge of edges) incoming[edge.to] = incoming[edge.to] + 1;
  const queue = states.filter((state) => incoming[state.id] === 0).map((state) => state.id);
  const visits = states.map(() => 0n);
  visits[0] = 1n;
  let workflowStarts = 0n;
  let emittedEvents = 0n;
  for (let index = 0; index < queue.length; index++) {
    const node = queue[index];
    const count = visits[node];
    workflowStarts += count * BigInt(states[node].matches.length);
    for (const edge of outgoing[node]) {
      emittedEvents += count;
      visits[edge.to] = visits[edge.to] + count;
      incoming[edge.to] = incoming[edge.to] - 1;
      if (incoming[edge.to] === 0) queue.push(edge.to);
    }
  }
  return { workflowStarts: workflowStarts.toString(), emittedEvents: emittedEvents.toString() };
}

// src/harness.ts
function object(value, at, allowed, required) {
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.getPrototypeOf(value) !== Object.prototype) throw new Error(`${at} must be an object.`);
  const result = value;
  for (const key2 of Object.keys(result)) if (!allowed.includes(key2)) throw new Error(`${at}: unsupported property ${JSON.stringify(key2)}.`);
  for (const key2 of required) if (!Object.hasOwn(result, key2)) throw new Error(`${at}.${key2} is required.`);
  return result;
}
function label(value, at, max) {
  if (typeof value !== "string" || !value.length || value.length > max || /[\u0000-\u001f\u007f]/u.test(value)) throw new Error(`${at} must be nonempty text, at most ${max} characters, without control characters.`);
}
function list2(value, at, min) {
  if (!Array.isArray(value) || value.length < min || value.length > 8) throw new Error(`${at} must contain ${min}\u20138 items.`);
  return value;
}
function validateSignal(value) {
  return validateBlueprint({ version: 1, name: "Harness signal validation", seed: value, workflows: [] }).seed;
}
function validateMatch(value, at) {
  const match = object(value, at, ["resource", "event", "data"], ["resource", "event"]);
  validateSignal({ resource: match.resource, event: match.event, data: Object.hasOwn(match, "data") ? match.data : {} });
  return value;
}
function parseSuite(text2) {
  if (typeof text2 !== "string" || text2.length > MAX_TEXT) throw new Error("Suite text exceeds 200,000 characters.");
  let value;
  try {
    value = JSON.parse(text2);
  } catch {
    throw new Error("Suite is not valid JSON. Check commas, quotes and brackets.");
  }
  return validateSuite(value);
}
function validateSuite(value) {
  const suite = object(value, "Suite", ["version", "name", "cases"], ["version", "name", "cases"]);
  if (suite.version !== 1) throw new Error("Only suite version 1 is supported.");
  label(suite.name, "Suite.name", 200);
  const ids = /* @__PURE__ */ new Set();
  for (const [index, item] of list2(suite.cases, "Suite.cases", 1).entries()) {
    const at = `Suite.cases[${index}]`;
    const scenario = object(item, at, ["id", "name", "seed", "required", "forbidden"], ["id", "name", "seed", "required"]);
    label(scenario.id, `${at}.id`, 64);
    label(scenario.name, `${at}.name`, 200);
    if (ids.has(scenario.id)) throw new Error(`Duplicate scenario ID: ${JSON.stringify(scenario.id)}.`);
    ids.add(scenario.id);
    validateSignal(scenario.seed);
    for (const [checkIndex, match] of list2(scenario.required, `${at}.required`, 1).entries()) validateMatch(match, `${at}.required[${checkIndex}]`);
    if (Object.hasOwn(scenario, "forbidden")) for (const [checkIndex, match] of list2(scenario.forbidden, `${at}.forbidden`, 0).entries()) validateMatch(match, `${at}.forbidden[${checkIndex}]`);
  }
  return structuredClone(value);
}
function matches2(signal, match) {
  return signal.resource === match.resource && signal.event === match.event && Object.entries(match.data ?? {}).every(([key2, value]) => Object.hasOwn(signal.data, key2) && signal.data[key2] === value);
}
function review(analysis, scenario) {
  const check = (match) => ({ match: structuredClone(match), observed: analysis.transitions.some((edge) => matches2(analysis.states[edge.to], match)) });
  const required = scenario.required.map(check);
  const forbidden = (scenario.forbidden ?? []).map(check);
  let status;
  let reason;
  if (analysis.status === "loop-found") {
    status = "blocked";
    reason = analysis.reason;
  } else if (forbidden.some((outcome) => outcome.observed)) {
    status = "blocked";
    reason = "A forbidden emitted signal was observed in this model.";
  } else if (!analysis.complete) {
    status = "inconclusive";
    reason = analysis.reason;
  } else if (required.some((outcome) => !outcome.observed)) {
    status = "blocked";
    reason = "The model settles, but one or more required emitted signals were not observed.";
  } else {
    status = "review-required";
    reason = "The model settles and fulfills this scenario\u2019s declared outcomes. Operator review is still required.";
  }
  return { status, analysisStatus: analysis.status, complete: analysis.complete, reason, stats: { ...analysis.stats }, required, forbidden };
}
function rehearse(baseline, candidate, input, budget = {}) {
  const suite = validateSuite(input);
  validateBlueprint(baseline);
  validateBlueprint(candidate);
  const designs = suite.cases.map((scenario) => ({
    scenario,
    baseline: validateBlueprint({ ...baseline, seed: scenario.seed }),
    candidate: validateBlueprint({ ...candidate, seed: scenario.seed })
  }));
  let resolvedBudget;
  const cases = designs.map((design) => {
    const before = analyze(design.baseline, budget);
    const after = analyze(design.candidate, budget);
    resolvedBudget = before.budget;
    return { id: design.scenario.id, name: design.scenario.name, seed: structuredClone(design.scenario.seed), required: structuredClone(design.scenario.required), forbidden: structuredClone(design.scenario.forbidden ?? []), baseline: review(before, design.scenario), candidate: review(after, design.scenario) };
  });
  const status = cases.some((item) => item.candidate.status === "blocked") ? "blocked" : cases.some((item) => item.candidate.status === "inconclusive") ? "inconclusive" : "review-required";
  return {
    schema: "triggertangle.harness/v1",
    name: suite.name,
    status,
    executionAllowed: false,
    budget: resolvedBudget,
    cases,
    regressions: cases.filter((item) => item.baseline.status === "review-required" && item.candidate.status !== "review-required").map((item) => item.id),
    notes: [
      "Design rehearsal only. No accounts, tools or workflows were connected or executed. No result grants execution, deployment or operating-system authority.",
      "The scenario suite must be owned and reviewed by the operator. An agent that can weaken these requirements can weaken this check.",
      "Each scenario replaces both designs\u2019 original seed. Required and forbidden outcomes match reachable emitted signals, never the initial seed.",
      "Outcome checks establish reachability, not delivery counts or final business-record state. Multiple deliveries may merge into one unique signal state.",
      "Unobserved outputs in incomplete explorations remain unknown. Workflow and delivery totals are unavailable for loops or incomplete exploration.",
      "Results cover only these seeds and declared rules. Retries, timing, concurrency, stored records, platform behavior and LLM decisions are not modeled.",
      "Review-required means the declared model checks passed; real-platform testing and the existing approval process are still required."
    ]
  };
}

// src/read-input.ts
import { open, stat } from "node:fs/promises";
async function readInput(path) {
  if (!(await stat(path)).isFile()) throw new Error("Input must be a regular UTF-8 JSON file.");
  const file = await open(path, "r");
  try {
    const info = await file.stat();
    const maximum = MAX_TEXT * 4;
    if (!info.isFile() || info.size > maximum) throw new Error("Input must be a regular file of at most 800,000 bytes.");
    const bytes = Buffer.alloc(maximum + 1);
    let length = 0;
    while (length < bytes.length) {
      const read = await file.read(bytes, length, bytes.length - length, length);
      if (!read.bytesRead) break;
      length += read.bytesRead;
    }
    if (length > maximum) throw new Error("Input exceeds 800,000 bytes.");
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes.subarray(0, length));
  } finally {
    await file.close();
  }
}

// src/version.ts
var VERSION = "0.3.0";

// src/harness-cli.ts
var HELP = `TriggerTangle Harness ${VERSION} \u2014 review a proposed workflow change

Usage: node trigger-tangle-harness.mjs --baseline before.json --candidate after.json --suite scenarios.json

--max-states N       Per-scenario budget, 1\u2013512 (default 256)
--max-transitions N  Per-scenario budget, 1\u20138192 (default 2048)
--help              Show this help

JSON goes to stdout. Exit 0: review-required; 1: blocked; 2: inconclusive;
3: invalid input/error. Exit 0 never grants approval or execution authority.
The operator owns the suite; candidate changes must not edit its requirements.
Tests declared emitted outcomes for up to 8 separate starting events.
No accounts, model calls, commands from inputs, or workflow execution.
Inputs remain unchanged. Reports contain the supplied inputs and sample data.
`;
async function main(args) {
  if (args.length === 1 && ["--help", "-h"].includes(args[0])) {
    process.stdout.write(HELP);
    return;
  }
  const options = /* @__PURE__ */ new Map();
  for (let index = 0; index < args.length; index += 2) {
    const option = args[index];
    if (!["--baseline", "--candidate", "--suite", "--max-states", "--max-transitions"].includes(option)) throw new Error(`Unknown option: ${JSON.stringify(option)}.`);
    if (options.has(option)) throw new Error(`Repeated option: ${option}.`);
    const value = args[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`Missing value for ${option}.`);
    options.set(option, value);
  }
  const baselinePath = options.get("--baseline");
  const candidatePath = options.get("--candidate");
  const suitePath = options.get("--suite");
  if (!baselinePath || !candidatePath || !suitePath) throw new Error("Supply --baseline, --candidate and an operator-owned --suite.");
  const budget = {};
  for (const [option, field2] of [["--max-states", "maxStates"], ["--max-transitions", "maxTransitions"]]) {
    const value = options.get(option);
    if (value !== void 0) {
      if (!/^\d+$/.test(value)) throw new Error(`${option} must be a whole number.`);
      budget[field2] = Number(value);
    }
  }
  const [baselineText, candidateText, suiteText] = await Promise.all([baselinePath, candidatePath, suitePath].map(readInput));
  const baseline = parseBlueprint(baselineText);
  const candidate = parseBlueprint(candidateText);
  const suite = parseSuite(suiteText);
  const report = rehearse(baseline, candidate, suite, budget);
  const digest = (value) => createHash("sha256").update(value, "utf8").digest("hex");
  process.stdout.write(`${JSON.stringify({
    ...report,
    evidence: {
      runnerVersion: VERSION,
      baselineTextSha256: digest(baselineText),
      candidateTextSha256: digest(candidateText),
      suiteTextSha256: digest(suiteText)
    },
    inputs: { baseline, candidate, suite }
  }, null, 2)}
`);
  process.exitCode = report.status === "review-required" ? 0 : report.status === "blocked" ? 1 : 2;
}
main(process.argv.slice(2)).catch((error) => {
  process.stderr.write(`TriggerTangle Harness: ${JSON.stringify(error instanceof Error ? error.message : "Rehearsal failed.")}
`);
  process.exitCode = 3;
});
