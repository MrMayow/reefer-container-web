"""Точный метод ветвей и границ с ограничением числа просмотренных узлов."""

from model import evaluate, integer_option, placement_options, verified_assignment


def solve_branch_bound(task, options=None):
    """Подтверждает минимальную стоимость только после завершения всего поиска."""
    checked = evaluate(task)
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("Параметры метода должны быть объектом JSON.")
    node_limit = integer_option(options, "nodeLimit", 100_000, 1, 1_000_000)

    containers = task["containers"]
    sites = task["sites"]
    n, m = len(containers), len(sites)
    site_index = {site["id"]: j for j, site in enumerate(sites)}
    choices, costs = placement_options(task)
    choices = [sorted(row, key=lambda j: costs[i][j]) for i, row in enumerate(choices)]

    # Сначала контейнеры с меньшим числом вариантов и большей нагрузкой.
    order = sorted(range(n), key=lambda i: (len(choices[i]),
                                             -containers[i]["weight"] - containers[i]["power"]))
    root_bound = sum(costs[i][row[0]] for i, row in enumerate(choices)) if all(choices) else None

    current_assignment = task["assignment"]
    best = ([site_index[current_assignment[c["id"]]] for c in containers]
            if checked["valid"] else None)
    best_cost = checked["totalCost"] if checked["valid"] else None
    initial_source = "текущий ручной план" if checked["valid"] else "без начального плана"
    plan = [-1] * n
    counts, weights, powers = [0] * m, [0] * m, [0] * m
    nodes = pruned_bound = pruned_capacity = 0
    improvements = 0
    stopped = False
    history = []
    tree = []
    tree_limit = 500
    tree_truncated = False
    checkpoint = max(1, node_limit // 60)

    def trace(parent, depth, cost, site, status, bound=None):
        """Сохраняет первые шаги поиска; размер схемы не ограничивает сам поиск."""
        nonlocal tree_truncated
        if len(tree) >= tree_limit:
            tree_truncated = True
            return None
        tree.append({"parent": parent, "depth": depth, "cost": cost,
                     "container": containers[order[depth - 1]]["id"] if depth else None,
                     "site": sites[site]["id"] if site is not None else None,
                     "status": status, "lowerBound": bound, "bestCost": best_cost})
        return len(tree) - 1

    def record(event, depth):
        snapshot = {"event": event, "nodesVisited": nodes,
                    "prunedBound": pruned_bound, "prunedCapacity": pruned_capacity,
                    "improvements": improvements,
                    "depth": depth, "bestCost": best_cost,
                    "bestChromosome": best[:] if best is not None else None}
        if len(history) < 119:
            history.append(snapshot)
        else:
            history[-1] = snapshot

    def fits(i, j):
        return (counts[j] < sites[j]["places"]
                and weights[j] + containers[i]["weight"] <= sites[j]["massLimit"]
                and powers[j] + containers[i]["power"] <= sites[j]["powerLimit"])

    def search(depth, cost, parent=None, site=None):
        nonlocal nodes, pruned_bound, pruned_capacity, improvements, stopped, best, best_cost
        if nodes >= node_limit:
            stopped = True
            trace(parent, depth, cost, site, "limit")
            return
        nodes += 1
        if nodes % checkpoint == 0:
            record("Промежуточный этап", depth)

        # Нижняя оценка: каждый оставшийся контейнер независимо выбирает
        # самое дешевое место среди еще подходящих. Общий расход пока не суммируется.
        bound = cost
        for next_depth in range(depth, n):
            i = order[next_depth]
            available = next((j for j in choices[i] if fits(i, j)), None)
            if available is None:
                pruned_capacity += 1
                trace(parent, depth, cost, site, "capacity")
                return
            bound += costs[i][available]
        if best_cost is not None and bound >= best_cost:
            pruned_bound += 1
            trace(parent, depth, cost, site, "bound", bound)
            return

        if depth == n:
            best = plan[:]
            best_cost = cost
            improvements += 1
            trace(parent, depth, cost, site, "plan", bound)
            record("Найден лучший план", depth)
            return

        node = trace(parent, depth, cost, site, "branch", bound)
        i = order[depth]
        # Сначала назначение лучшего плана, затем остальные площадки по стоимости.
        branches = sorted(choices[i], key=lambda j: j != best[i]) if best is not None else choices[i]
        for j in branches:
            if not fits(i, j):
                pruned_capacity += 1
                trace(node, depth + 1, cost + costs[i][j], j, "capacity")
                continue
            plan[i] = j
            counts[j] += 1
            weights[j] += containers[i]["weight"]
            powers[j] += containers[i]["power"]
            search(depth + 1, cost + costs[i][j], node, j)
            counts[j] -= 1
            weights[j] -= containers[i]["weight"]
            powers[j] -= containers[i]["power"]
            plan[i] = -1
            if stopped:
                return

    record(f"Начало поиска: {initial_source}", 0)
    impossible = (root_bound is None
                  or sum(site["places"] for site in sites) < n
                  or sum(site["massLimit"] for site in sites) < sum(c["weight"] for c in containers)
                  or sum(site["powerLimit"] for site in sites) < sum(c["power"] for c in containers))
    if not impossible:
        search(0, 0)
    else:
        trace(None, 0, 0, None, "capacity")

    assignment = verified_assignment(task, best, best_cost) if best is not None else None

    if stopped:
        status = "limit_with_plan" if best is not None else "limit_no_plan"
        message = ("Лимит узлов: поиск не завершен."
                   if best is not None else
                   "Лимит узлов: план не найден, отсутствие решения не доказано.")
    elif best is None:
        status = "infeasible"
        message = "Допустимого размещения нет."
    else:
        status = "optimal"
        message = ""
    record(message or "Поиск завершен.", 0)
    answer = {"method": "branch_bound", "implemented": True, "status": status,
              "message": message, "provenOptimal": status == "optimal",
              "provenInfeasible": status == "infeasible",
              "rootLowerBound": root_bound, "nodesVisited": nodes,
              "improvements": improvements,
              "prunedBound": pruned_bound, "prunedCapacity": pruned_capacity,
              "nodeLimit": node_limit, "history": history,
              "tree": tree, "treeLimit": tree_limit, "treeTruncated": tree_truncated}
    answer["initialSource"] = initial_source
    if best is not None:
        answer["bestCost"] = best_cost
        answer["bestAssignment"] = assignment
    return answer
