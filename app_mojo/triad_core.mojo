"""
triad_core.mojo
Native Mojo Pareto frontier dominance ranker and 3D multi-objective optimizer.
Evaluates agent workflows across Reliability (pass rate), Duration (latency), and Cost (token expenditure).
Adapted for Buzburg SwarmMojo.
"""

from std.collections import List

comptime DEFAULT_MIN_RELIABILITY: Float64 = 0.85
comptime DEFAULT_MAX_DURATION_S: Float64 = 120.0


@fieldwise_init
struct WorkflowMetric(Copyable, Movable):
    var id: String
    var reliability: Float64
    var duration_s: Float64
    var cost_tokens: Int
    var passed: Bool


@fieldwise_init
struct ParetoRankResult(Copyable, Movable):
    var is_viable: Bool
    var is_dominated: Bool
    var composite_score: Float64
    var harmonic_score: Float64


def dominates(a: WorkflowMetric, b: WorkflowMetric) -> Bool:
    """
    Returns True if metric 'a' strictly Pareto-dominates metric 'b'.
    Objective 1: Reliability (maximize)
    Objective 2: Duration (minimize)
    Objective 3: Cost tokens (minimize)
    """
    if not a.passed and b.passed:
        return False
    if a.passed and not b.passed:
        return True

    var not_worse = (
        a.reliability >= b.reliability
        and a.duration_s <= b.duration_s
        and a.cost_tokens <= b.cost_tokens
    )

    var strictly_better = (
        a.reliability > b.reliability
        or a.duration_s < b.duration_s
        or a.cost_tokens < b.cost_tokens
    )

    return not_worse and strictly_better


def compute_composite_score(
    reliability: Float64,
    duration_s: Float64,
    cost_tokens: Int,
    max_duration_s: Float64,
    max_cost_tokens: Int,
) -> Float64:
    """
    Weighted composite score:
    0.50 * reliability + 0.30 * (1.0 - norm_duration) + 0.20 * (1.0 - norm_cost)
    """
    var effective_max_dur = max_duration_s if max_duration_s > 0.0 else 1.0
    var effective_max_cost = Float64(max_cost_tokens) if max_cost_tokens > 0 else 1.0

    var norm_dur = duration_s / effective_max_dur
    if norm_dur > 1.0:
        norm_dur = 1.0

    var norm_cost = Float64(cost_tokens) / effective_max_cost
    if norm_cost > 1.0:
        norm_cost = 1.0

    var dur_score = 1.0 - norm_dur
    var cost_score = 1.0 - norm_cost

    return (0.50 * reliability) + (0.30 * dur_score) + (0.20 * cost_score)


def compute_harmonic_score(
    reliability: Float64,
    norm_duration: Float64,
    norm_cost: Float64,
) -> Float64:
    """
    Harmonic mean of three efficiency dimensions.
    Penalizes extreme imbalances where one dimension collapses.
    """
    var r = reliability if reliability > 0.001 else 0.001
    var d = (1.0 - norm_duration) if norm_duration < 0.999 else 0.001
    var c = (1.0 - norm_cost) if norm_cost < 0.999 else 0.001

    var sum_inv = (1.0 / r) + (1.0 / d) + (1.0 / c)
    return 3.0 / sum_inv


def evaluate_candidate(
    candidate: WorkflowMetric,
    population: List[WorkflowMetric],
    min_reliability: Float64 = DEFAULT_MIN_RELIABILITY,
    max_duration_s: Float64 = DEFAULT_MAX_DURATION_S,
    max_cost_tokens: Int = 100000,
) -> ParetoRankResult:
    """
    Evaluates viability, Pareto dominance, and composite score of candidate against population.
    """
    var viable = (
        candidate.passed
        and candidate.reliability >= min_reliability
        and candidate.duration_s <= max_duration_s
    )

    var dominated = False
    for i in range(len(population)):
        if dominates(population[i], candidate):
            dominated = True
            break

    var comp_score = compute_composite_score(
        candidate.reliability,
        candidate.duration_s,
        candidate.cost_tokens,
        max_duration_s,
        max_cost_tokens,
    )

    var norm_dur = candidate.duration_s / (max_duration_s if max_duration_s > 0.0 else 1.0)
    var norm_cost = Float64(candidate.cost_tokens) / (Float64(max_cost_tokens) if max_cost_tokens > 0 else 1.0)
    var harm_score = compute_harmonic_score(candidate.reliability, norm_dur, norm_cost)

    return ParetoRankResult(
        is_viable=viable,
        is_dominated=dominated,
        composite_score=comp_score,
        harmonic_score=harm_score,
    )
