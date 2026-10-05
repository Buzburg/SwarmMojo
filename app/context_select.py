"""Portable reference implementation of the native Mojo context selector."""

def select_context(costs: list[int], utilities: list[int], budget: int, required: int = -1) -> list[int]:
    n = len(costs)
    if n != len(utilities) or n > 64 or type(budget) is not int or not 0 <= budget <= 20000:
        raise ValueError('Invalid context selector dimensions or budget')
    if type(required) is not int or not -1 <= required < n:
        raise ValueError('Invalid required record')
    if any(type(cost) is not int or not 1 <= cost <= 20000 for cost in costs):
        raise ValueError('Invalid record cost')
    if any(type(value) is not int or not 1 <= value <= 1000000 for value in utilities):
        raise ValueError('Invalid record utility')
    if required >= 0 and costs[required] > budget:
        raise ValueError('Required record cannot fit')
    if sum(costs) <= budget:
        return list(range(n))
    remaining = budget - (costs[required] if required >= 0 else 0)
    width = remaining + 1
    scores = [0] * width
    decisions = bytearray(n * width)
    for index, (weight, value) in enumerate(zip(costs, utilities)):
        if index == required:
            continue
        offset = index * width
        for capacity in range(remaining, weight - 1, -1):
            proposed = scores[capacity - weight] + value
            if proposed > scores[capacity]:
                scores[capacity] = proposed
                decisions[offset + capacity] = 1
    chosen = {required} if required >= 0 else set()
    capacity = remaining
    for index in range(n - 1, -1, -1):
        if decisions[index * width + capacity]:
            chosen.add(index)
            capacity -= costs[index]
    return sorted(chosen)
