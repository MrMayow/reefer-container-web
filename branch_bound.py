"""Точный метод ветвей и границ с ограничением числа просмотренных узлов."""

from model import evaluate, integer_option, placement_options, verified_assignment


def solve_branch_bound(task, options=None):
    """Возвращает доказанный оптимум только после завершения всего поиска."""
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
    suffix_min = [0] * (n + 1)
    if all(choices):
        for depth in range(n - 1, -1, -1):
            i = order[depth]
            suffix_min[depth] = suffix_min[depth + 1] + costs[i][choices[i][0]]
        root_bound = suffix_min[0]
    else:
        root_bound = None

    current_assignment = task["assignment"]
    best = ([site_index[current_assignment[c["id"]]] for c in containers]
            if checked["valid"] else None)
    best_cost = checked["totalCost"] if checked["valid"] else None
    initial_source = "текущий ручной план" if checked["valid"] else "без начального плана"
    provided = options.get("incumbentAssignment")
    if provided is not None:
        if not isinstance(provided, dict):
            raise ValueError("incumbentAssignment: ожидается назначение контейнеров по площадкам.")
        candidate_check = evaluate({**task, "assignment": provided})
        if not candidate_check["valid"]:
            raise ValueError("Переданный начальный план нарушает ограничения задачи.")
        if best_cost is None or candidate_check["totalCost"] < best_cost:
            best = [site_index[provided[c["id"]]] for c in containers]
            best_cost = candidate_check["totalCost"]
            initial_source = "переданный допустимый план"
    plan = [-1] * n
    counts, weights, powers = [0] * m, [0] * m, [0] * m
    nodes = pruned_bound = pruned_capacity = 0
    stopped = False
    history = []
    checkpoint = max(1, node_limit // 60)

    def record(event, depth):
        snapshot = {"event": event, "nodesVisited": nodes,
                    "prunedBound": pruned_bound, "prunedCapacity": pruned_capacity,
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

    def search(depth, cost):
        nonlocal nodes, pruned_bound, pruned_capacity, stopped, best, best_cost
        if nodes >= node_limit:
            stopped = True
            return
        nodes += 1
        if nodes % checkpoint == 0:
            record("Промежуточный этап", depth)

        # Даже если каждый оставшийся контейнер попадёт на свою самую дешёвую
        # площадку, эта ветвь не может улучшить известный план.
        if best_cost is not None and cost + suffix_min[depth] >= best_cost:
            pruned_bound += 1
            return

        # Более сильная нижняя оценка учитывает уже занятые ресурсы, но
        # допускает, что несколько контейнеров используют один и тот же остаток.
        optimistic = cost
        for next_depth in range(depth, n):
            i = order[next_depth]
            available = next((j for j in choices[i] if fits(i, j)), None)
            if available is None:
                pruned_capacity += 1
                return
            optimistic += costs[i][available]
        if best_cost is not None and optimistic >= best_cost:
            pruned_bound += 1
            return

        if depth == n:
            best = plan[:]
            best_cost = cost
            record("Найден лучший допустимый план", depth)
            return

        i = order[depth]
        for j in choices[i]:
            if not fits(i, j):
                pruned_capacity += 1
                continue
            plan[i] = j
            counts[j] += 1
            weights[j] += containers[i]["weight"]
            powers[j] += containers[i]["power"]
            search(depth + 1, cost + costs[i][j])
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

    assignment = verified_assignment(task, best, best_cost) if best is not None else None

    if stopped:
        status = "limit_with_plan" if best is not None else "limit_no_plan"
        message = ("Достигнут лимит узлов. Показан лучший найденный допустимый план; оптимальность не доказана."
                   if best is not None else
                   "Достигнут лимит узлов. Допустимый план пока не найден; отсутствие решения не доказано.")
    elif best is None:
        status = "infeasible"
        message = "Все варианты отсечены или проверены: допустимого размещения нет."
    else:
        status = "optimal"
        message = "Все оставшиеся ветви проверены или отсечены: глобальный оптимум доказан."
    record(message, 0)
    answer = {"method": "branch_bound", "implemented": True, "status": status,
              "message": message, "provenOptimal": status == "optimal",
              "provenInfeasible": status == "infeasible",
              "rootLowerBound": root_bound, "nodesVisited": nodes,
              "prunedBound": pruned_bound, "prunedCapacity": pruned_capacity,
              "nodeLimit": node_limit, "history": history}
    answer["initialSource"] = initial_source
    if best is not None:
        answer["bestCost"] = best_cost
        answer["bestAssignment"] = assignment
    return answer
