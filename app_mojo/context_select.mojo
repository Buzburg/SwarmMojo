"""Bounded 0/1 context packing. No Python calls, storage or model dependency."""

def select_context(costs: List[Int], utilities: List[Int], budget: Int, required: Int = -1) raises -> List[Int]:
    var n = len(costs)
    if n != len(utilities) or n > 64 or budget < 0 or budget > 20000:
        raise Error("Invalid context selector dimensions or budget")
    if required < -1 or required >= n:
        raise Error("Invalid required record")
    var total = 0
    for i in range(n):
        if costs[i] < 1 or costs[i] > 20000 or utilities[i] < 1 or utilities[i] > 1000000:
            raise Error("Invalid record cost or utility")
        total += costs[i]
    var selected = List[Int]()
    if required >= 0 and costs[required] > budget:
        raise Error("Required record cannot fit")
    if total <= budget:
        for i in range(n):
            selected.append(i)
        return selected^
    var remaining = budget
    if required >= 0:
        remaining -= costs[required]
    var width = remaining + 1
    var scores = List[Int](capacity=width)
    for _ in range(width):
        scores.append(0)
    var decisions = List[Bool](capacity=n * width)
    for _ in range(n * width):
        decisions.append(False)
    for i in range(n):
        if i == required:
            continue
        var weight = costs[i]
        var value = utilities[i]
        for capacity in range(remaining, weight - 1, -1):
            var proposed = scores[capacity - weight] + value
            if proposed > scores[capacity]:
                scores[capacity] = proposed
                decisions[i * width + capacity] = True
    var chosen = List[Bool](capacity=n)
    for i in range(n):
        chosen.append(i == required)
    var capacity = remaining
    for i in range(n - 1, -1, -1):
        if decisions[i * width + capacity]:
            chosen[i] = True
            capacity -= costs[i]
    for i in range(n):
        if chosen[i]:
            selected.append(i)
    return selected^
