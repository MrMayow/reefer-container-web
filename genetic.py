"""Генетический поиск допустимого размещения без сторонних библиотек."""

import random

from model import evaluate, integer_option, placement_options, verified_assignment


def solve_genetic(task, options=None):
    """Ищет допустимый план; история хранит популяции и действия каждого поколения."""
    evaluate(task)  # Проверка структуры и целочисленных исходных данных.
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("Параметры алгоритма должны быть объектом JSON.")
    generations = integer_option(options, "generations", 60, 1, 200)
    population_size = integer_option(options, "populationSize", 36, 4, 80)
    seed = integer_option(options, "seed", 26, 0, 999999)
    selection_method = options.get("selectionMethod", "tournament")
    if selection_method not in ("tournament", "best_half"):
        raise ValueError("Способ отбора: выберите турнир или лучшую половину.")
    mutation_enabled = options.get("mutationEnabled", True)
    if type(mutation_enabled) is not bool:
        raise ValueError("Включение мутаций должно быть логическим значением.")
    mutation_type = options.get("mutationType", "swap")
    if mutation_type not in ("move", "swap"):
        raise ValueError("Тип мутации: выберите перенос или обмен.")
    mutation_probability = integer_option(options, "mutationProbability", 60, 0, 100)
    rng = random.Random(seed)

    containers = task["containers"]
    sites = task["sites"]
    n, m = len(containers), len(sites)
    site_index = {site["id"]: index for index, site in enumerate(sites)}
    allowed, costs = placement_options(task)

    def plan_cost(plan):
        return sum(costs[i][j] for i, j in enumerate(plan))

    def feasible(plan):
        if len(plan) != n:
            return False
        counts, weights, powers = [0] * m, [0] * m, [0] * m
        for i, j in enumerate(plan):
            if j not in allowed[i]:
                return False
            counts[j] += 1
            weights[j] += containers[i]["weight"]
            powers[j] += containers[i]["power"]
        return all(counts[j] <= sites[j]["places"]
                   and weights[j] <= sites[j]["massLimit"]
                   and powers[j] <= sites[j]["powerLimit"] for j in range(m))

    def construct(preferred=None, max_nodes=5000, excluded=()):
        """Собирает допустимый план; при исправлении сначала пробует назначения потомка."""
        plan = [-1] * n
        counts, weights, powers = [0] * m, [0] * m, [0] * m
        order = list(range(n))
        rng.shuffle(order)
        order.sort(key=lambda i: (len(allowed[i]),
                                  -containers[i]["weight"] - containers[i]["power"]))
        options_by_container = []
        for i in order:
            choices = allowed[i][:]
            rng.shuffle(choices)
            if rng.random() < 0.5:
                choices.sort(key=lambda j: costs[i][j])
            if preferred is not None and preferred[i] in choices:
                choices.remove(preferred[i])
                choices.insert(0, preferred[i])
            options_by_container.append(choices)

        visited = 0
        limited = False

        def fill(depth):
            nonlocal visited, limited
            if depth == n:
                return tuple(plan) not in excluded
            i = order[depth]
            for j in options_by_container[depth]:
                if visited >= max_nodes:
                    limited = True
                    return False
                visited += 1
                if (counts[j] < sites[j]["places"]
                        and weights[j] + containers[i]["weight"] <= sites[j]["massLimit"]
                        and powers[j] + containers[i]["power"] <= sites[j]["powerLimit"]):
                    plan[i] = j
                    counts[j] += 1
                    weights[j] += containers[i]["weight"]
                    powers[j] += containers[i]["power"]
                    if fill(depth + 1):
                        return True
                    plan[i] = -1
                    counts[j] -= 1
                    weights[j] -= containers[i]["weight"]
                    powers[j] -= containers[i]["power"]
            return False

        found = fill(0)
        return (tuple(plan) if found else None), visited, limited

    discarded = set()  # Планы, выбывшие из популяции, не возвращаются в этом запуске.
    plans, plan_ids = [], {}

    def plan_id(plan):
        """В истории хранятся номера планов, сами хромосомы записываются один раз."""
        if plan not in plan_ids:
            plan_ids[plan] = len(plans)
            valid = feasible(plan)
            plans.append({"chromosome": list(plan), "valid": valid,
                          "cost": plan_cost(plan) if valid else None})
        return plan_ids[plan]

    def mutate(plan):
        """Пробует выбранный тип мутации и возвращает допустимый вариант."""
        retired_skips = 0
        for attempt in range(1, 13):
            changed = list(plan)
            i = rng.randrange(n)
            if mutation_type == "move":
                j = rng.randrange(m)
                if j == changed[i]:
                    continue
                changed[i] = j
            elif n > 1:
                k = rng.randrange(n)
                if k == i or changed[k] == changed[i]:
                    continue
                changed[i], changed[k] = changed[k], changed[i]
            changed = tuple(changed)
            if changed in discarded:
                retired_skips += 1
            elif feasible(changed):
                return changed, attempt, retired_skips
        return plan, 12, retired_skips

    current = task["assignment"]
    initial = tuple(site_index.get(current.get(c["id"]), -1) for c in containers)
    population = [initial] if feasible(initial) else []
    events = [{"kind": "manual", "result": plan_id(initial), "status": "accepted"}] if population else []
    initial_attempts = initial_nodes = 0
    initial_budget = 50_000_000
    for _ in range(population_size * 20):
        if len(population) >= population_size or initial_nodes >= initial_budget:
            break
        candidate, nodes, limited = construct(
            max_nodes=min(100_000, initial_budget - initial_nodes), excluded=population)
        initial_attempts += 1
        initial_nodes += nodes
        events.append({"kind": "initial", "result": plan_id(candidate) if candidate is not None else None,
                       "status": "accepted" if candidate is not None else "not_found",
                       "nodes": nodes, "limited": limited})
        if candidate is not None:
            population.append(candidate)
        elif not limited:
            break  # Поиск завершён: других допустимых размещений нет.
    if not population:
        return {"method": "genetic", "implemented": True, "status": "not_found",
                "provenOptimal": False, "message": "Допустимый план не найден. Это не доказывает, что его нет.",
                "history": [], "generationsRun": 0, "populationSize": population_size,
                "initialAttempts": initial_attempts, "initialNodesVisited": initial_nodes,
                "seed": seed, "selectionMethod": selection_method,
                "mutationEnabled": mutation_enabled, "mutationType": mutation_type,
                "mutationProbability": mutation_probability}
    best = min(population, key=plan_cost)
    history = []
    used_parents = set()
    carried_over = 0
    parent_pool = []
    retired_now = []

    def record(generation, crossovers, mutations, repairs):
        history.append({"generation": generation, "bestCost": plan_cost(best),
                        "bestChromosome": list(best), "distinctPlans": len(set(population)),
                        "populationCount": len(population),
                        "crossovers": crossovers, "mutations": mutations,
                        "repairs": repairs, "parentsUsed": len(used_parents),
                        "carriedOver": carried_over,
                        "immediateReserves": sum(event["kind"] == "reserve" for event in events),
                        "population": [plan_id(plan) for plan in population],
                        "parentPool": [plan_id(plan) for plan in parent_pool],
                        "discarded": [plan_id(plan) for plan in retired_now],
                        "discardedCount": len(discarded), "events": events})

    record(0, 0, 0, 0)

    def select(parent_pool):
        if selection_method == "best_half":
            return rng.choice(parent_pool), []
        participants = rng.sample(parent_pool, min(3, len(parent_pool)))
        return min(participants, key=plan_cost), participants

    for generation in range(1, generations + 1):
        ordered_population = sorted(population, key=plan_cost)
        parent_pool = (ordered_population[:max(1, len(population) // 2)]
                       if selection_method == "best_half" else population)
        reserve_pool = (ordered_population[len(parent_pool):]
                        if selection_method == "best_half" else ordered_population)
        available_parents = parent_pool[:]
        new_population = [best]  # Элитизм: лучший план никогда не теряется.
        events = [{"kind": "elite", "result": plan_id(best), "status": "accepted"}]
        used_parents = set()
        carried_over = 0
        crossovers = mutations = repairs = 0
        for _ in range(population_size * 4):
            if len(new_population) >= population_size:
                break
            first, first_group = select(available_parents)
            second, second_group = select(available_parents)
            used_parents.update((first, second))
            preferred = tuple(first[i] if rng.random() < 0.5 else second[i] for i in range(n))
            crossovers += 1
            event = {"kind": "crossover", "parents": [plan_id(first), plan_id(second)],
                     "participants": [[plan_id(plan) for plan in group] for group in (first_group, second_group)],
                     "crossed": plan_id(preferred), "result": None, "status": "not_found"}
            events.append(event)
            if feasible(preferred):
                child = preferred
            else:
                child, nodes, limited = construct(preferred, excluded=set(new_population) | discarded)
                event.update(repaired=plan_id(child) if child is not None else None,
                             repairNodes=nodes, repairLimited=limited)
                if child is not None:
                    repairs += 1
                else:
                    event["reserve"] = None
                    for candidate in reserve_pool:
                        if candidate not in used_parents and candidate not in new_population:
                            new_population.append(candidate)
                            carried_over += 1
                            event["reserve"] = plan_id(candidate)
                            events.append({"kind": "reserve", "result": plan_id(candidate), "status": "accepted"})
                            # Резерв больше не выбирается родителем в этом поколении.
                            if candidate in available_parents:
                                available_parents.remove(candidate)
                            break
                    continue
            event["result"] = plan_id(child)
            if child in discarded:
                event["status"] = "retired"
                continue
            event["mutation"] = "skipped" if mutation_enabled else "disabled"
            if (mutation_enabled and mutation_probability > 0
                    and rng.random() < mutation_probability / 100):
                changed, attempts, retired_skips = mutate(child)
                event.update(mutation="changed" if changed != child else "unchanged",
                             mutationAttempts=attempts, mutationRetiredSkips=retired_skips)
                if changed != child:
                    mutations += 1
                    child = changed
            event["result"] = plan_id(child)
            if child in discarded:
                event["status"] = "retired"
            elif child in new_population:
                event["status"] = "duplicate"
            else:
                new_population.append(child)
                event["status"] = "accepted"
        # В режиме лучшей половины старые особи берутся только из нижней части.
        for candidate in reserve_pool:
            if len(new_population) >= population_size:
                break
            if candidate not in used_parents and candidate not in new_population:
                new_population.append(candidate)
                carried_over += 1
                events.append({"kind": "carry", "result": plan_id(candidate), "status": "accepted"})
        excluded_parents = set(parent_pool) if selection_method == "best_half" else used_parents
        while len(new_population) < population_size:
            candidate, nodes, limited = construct(excluded=set(new_population) | excluded_parents | discarded)
            events.append({"kind": "generate", "result": plan_id(candidate) if candidate is not None else None,
                           "status": "accepted" if candidate is not None else "not_found",
                           "nodes": nodes, "limited": limited})
            if candidate is None:
                break
            new_population.append(candidate)
        retired_now = [plan for plan in population if plan not in new_population]
        discarded.update(retired_now)
        population = new_population
        generation_best = min(population, key=plan_cost)
        if plan_cost(generation_best) < plan_cost(best):
            best = generation_best
        record(generation, crossovers, mutations, repairs)

    best_cost = plan_cost(best)
    assignment = verified_assignment(task, best, best_cost)
    return {"method": "genetic", "implemented": True, "status": "found",
            "provenOptimal": False, "message": "Найден допустимый план. Минимальная стоимость не подтверждена.",
            "bestCost": best_cost, "bestAssignment": assignment,
            "history": history, "plans": plans, "generationsRun": generations,
            "populationSize": population_size, "seed": seed,
            "initialAttempts": initial_attempts, "initialNodesVisited": initial_nodes,
            "selectionMethod": selection_method,
            "mutationEnabled": mutation_enabled, "mutationType": mutation_type,
            "mutationProbability": mutation_probability}
