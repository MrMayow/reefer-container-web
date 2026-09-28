"""Полный перебор назначений контейнеров без отсечения ветвей."""

from itertools import product

from model import evaluate, placement_options, verified_assignment


def solve_exhaustive(task, options=None):
    """Проверяет каждое полное назначение и записывает этапы."""
    evaluate(task)  # Та же проверка целых исходных данных, что и у других методов.
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("Параметры метода должны быть объектом JSON.")
    containers = task["containers"]
    sites = task["sites"]
    n, m = len(containers), len(sites)
    total = m ** n
    choices, costs = placement_options(task)
    allowed = [set(row) for row in choices]

    checked_count = valid_count = 0
    best_cost = None
    best = None
    history = []
    checkpoint = max(1, total // 60)

    def record(event):
        stage = {"event": event, "checkedCount": checked_count,
                 "validCount": valid_count,
                 "invalidCount": checked_count - valid_count,
                 "bestCost": best_cost,
                 "bestChromosome": list(best) if best is not None else None}
        if len(history) < 119:
            history.append(stage)
        else:
            history[-1] = stage

    record("Начало перебора")
    # product создаёт назначения по одному. Каждая комбинация учитывается,
    # даже если она нарушает срок или ресурсы площадки.
    for plan in product(range(m), repeat=n):
        checked_count += 1
        counts = [0] * m
        weights = [0] * m
        powers = [0] * m
        feasible = True
        cost = 0
        for i, j in enumerate(plan):
            container = containers[i]
            site = sites[j]
            counts[j] += 1
            weights[j] += container["weight"]
            powers[j] += container["power"]
            if (j not in allowed[i] or counts[j] > site["places"]
                    or weights[j] > site["massLimit"]
                    or powers[j] > site["powerLimit"]):
                feasible = False
                break
            cost += costs[i][j]
        if feasible:
            valid_count += 1
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = plan
                record("Найден более дешёвый допустимый план")
        if checked_count % checkpoint == 0:
            record("Промежуточный этап")

    if best is not None:
        status = "optimal"
        message = "Все назначения проверены: глобальный оптимум доказан."
    else:
        status = "infeasible"
        message = "Все назначения проверены: допустимого размещения нет."
    record(message)

    answer = {"method": "exhaustive", "implemented": True, "status": status,
              "message": message, "provenOptimal": status == "optimal",
              "provenInfeasible": status == "infeasible",
              "totalCombinations": str(total),
              "checkedCount": checked_count, "validCount": valid_count,
              "invalidCount": checked_count - valid_count, "history": history}
    if best is not None:
        assignment = verified_assignment(task, best, best_cost)
        answer["bestCost"] = best_cost
        answer["bestAssignment"] = assignment
    return answer
