"""Полный перебор назначений контейнеров без отсечения ветвей."""

from itertools import product

from model import evaluate


def solve_exhaustive(task, options=None):
    """Проверяет каждое полное назначение до лимита и записывает этапы."""
    evaluate(task)  # Та же проверка целых исходных данных, что и у других методов.
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("Параметры метода должны быть объектом JSON.")
    combination_limit = options.get("combinationLimit", 1_000_000)
    if type(combination_limit) is not int or not 1 <= combination_limit <= 5_000_000:
        raise ValueError("combinationLimit: требуется целое число от 1 до 5000000.")

    containers = task["containers"]
    sites = task["sites"]
    n, m = len(containers), len(sites)
    total = m ** n
    limit_hours = task["limitHours"]
    ton_hour = task["tariffMode"] == "ton_hour"
    allowed = [[container["storage"] + site["travelTime"] <= limit_hours
                for site in sites] for container in containers]
    costs = [[container["storage"] * site["storageRate"]
              + (container["weight"] if ton_hour else 1)
              * site["travelTime"] * site["travelRate"]
              for site in sites] for container in containers]

    checked_count = valid_count = 0
    best_cost = None
    best = None
    history = []
    checkpoint = max(1, min(total, combination_limit) // 60)

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
        if checked_count >= combination_limit:
            break
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
            if (not allowed[i][j] or counts[j] > site["places"]
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

    complete = checked_count == total
    if complete and best is not None:
        status = "optimal"
        message = "Все назначения проверены: глобальный оптимум доказан."
    elif complete:
        status = "infeasible"
        message = "Все назначения проверены: допустимого размещения нет."
    elif best is not None:
        status = "limit_with_plan"
        message = "Достигнут лимит проверок. Показан лучший найденный план; оптимальность не доказана."
    else:
        status = "limit_no_plan"
        message = "Достигнут лимит проверок. Допустимый план пока не найден; отсутствие решения не доказано."
    record(message)

    answer = {"method": "exhaustive", "implemented": True, "status": status,
              "message": message, "provenOptimal": status == "optimal",
              "provenInfeasible": status == "infeasible",
              "totalCombinations": str(total), "combinationLimit": combination_limit,
              "checkedCount": checked_count, "validCount": valid_count,
              "invalidCount": checked_count - valid_count, "history": history}
    if best is not None:
        assignment = {container["id"]: sites[best[i]]["id"]
                      for i, container in enumerate(containers)}
        verification = evaluate({**task, "assignment": assignment})
        if not verification["valid"] or verification["totalCost"] != best_cost:
            raise RuntimeError("Ошибка внутренней проверки плана полного перебора.")
        answer["bestCost"] = best_cost
        answer["bestAssignment"] = assignment
    return answer
