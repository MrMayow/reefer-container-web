"""Генетический поиск допустимого размещения без сторонних библиотек."""

import random

from model import evaluate


def _option(options, name, default, minimum, maximum):
    value = options.get(name, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name}: требуется целое число от {minimum} до {maximum}.")
    return value


def solve_genetic(task, options=None):
    """Ищет допустимый план; история хранит лучший план после каждого поколения."""
    evaluate(task)  # Проверка структуры и целочисленных исходных данных.
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("Параметры алгоритма должны быть объектом JSON.")
    generations = _option(options, "generations", 60, 1, 200)
    population_size = _option(options, "populationSize", 36, 4, 80)
    seed = _option(options, "seed", 26, 0, 999999)
    selection_method = options.get("selectionMethod", "tournament")
    if selection_method not in ("tournament", "best_half"):
        raise ValueError("Способ отбора: выберите турнир или лучшую половину.")
    rng = random.Random(seed)

    containers = task["containers"]
    sites = task["sites"]
    n, m = len(containers), len(sites)
    site_index = {site["id"]: index for index, site in enumerate(sites)}
    allowed = []
    costs = []
    for container in containers:
        choices = [j for j, site in enumerate(sites)
                   if container["storage"] + site["travelTime"] <= task["limitHours"]
                   and site["places"] >= 1
                   and container["weight"] <= site["massLimit"]
                   and container["power"] <= site["powerLimit"]]
        allowed.append(choices)
        factor = container["weight"] if task["tariffMode"] == "ton_hour" else 1
        costs.append([container["storage"] * site["storageRate"]
                      + factor * site["travelTime"] * site["travelRate"] for site in sites])

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

    def construct(preferred=None):
        """Жадно собирает план с приоритетом родительских генов и трудных контейнеров."""
        plan = [-1] * n
        counts, weights, powers = [0] * m, [0] * m, [0] * m
        order = list(range(n))
        rng.shuffle(order)
        order.sort(key=lambda i: (len(allowed[i]),
                                  -containers[i]["weight"] - containers[i]["power"]))
        for i in order:
            choices = allowed[i][:]
            rng.shuffle(choices)
            choices.sort(key=lambda j: costs[i][j])
            if preferred is not None and preferred[i] in choices:
                choices.remove(preferred[i])
                choices.insert(0, preferred[i])
            if preferred is None and rng.random() < 0.55:
                rng.shuffle(choices)
            for j in choices:
                if (counts[j] < sites[j]["places"]
                        and weights[j] + containers[i]["weight"] <= sites[j]["massLimit"]
                        and powers[j] + containers[i]["power"] <= sites[j]["powerLimit"]):
                    plan[i] = j
                    counts[j] += 1
                    weights[j] += containers[i]["weight"]
                    powers[j] += containers[i]["power"]
                    break
            if plan[i] == -1:
                return None
        return tuple(plan)

    def mutate(plan):
        """Перенос или обмен; возвращает только допустимый вариант."""
        for _ in range(12):
            changed = list(plan)
            i = rng.randrange(n)
            if rng.random() < 0.5:
                j = rng.randrange(m)
                if j == changed[i]:
                    continue
                changed[i] = j
            elif n > 1:
                k = rng.randrange(n)
                if k == i or changed[k] == changed[i]:
                    continue
                changed[i], changed[k] = changed[k], changed[i]
            if feasible(changed):
                return tuple(changed)
        return plan

    current = task["assignment"]
    initial = tuple(site_index.get(current.get(c["id"]), -1) for c in containers)
    population = [initial] if feasible(initial) else []
    for _ in range(population_size * 12):
        if len(population) >= population_size:
            break
        candidate = construct()
        if candidate is not None:
            population.append(candidate)
    if not population:
        return {"method": "genetic", "implemented": True, "status": "not_found",
                "provenOptimal": False, "message": "Допустимый план не найден. Это не доказывает, что его нет.",
                "history": [], "generationsRun": 0, "populationSize": population_size,
                "seed": seed, "selectionMethod": selection_method}
    while len(population) < population_size:
        population.append(population[rng.randrange(len(population))])

    best = min(population, key=plan_cost)
    history = []

    def record(generation, crossovers, mutations, repairs):
        history.append({"generation": generation, "bestCost": plan_cost(best),
                        "bestChromosome": list(best), "distinctPlans": len(set(population)),
                        "crossovers": crossovers, "mutations": mutations,
                        "repairs": repairs})

    record(0, 0, 0, 0)

    def select(parent_pool):
        if selection_method == "best_half":
            return rng.choice(parent_pool)
        return min(rng.sample(parent_pool, 3), key=plan_cost)

    for generation in range(1, generations + 1):
        parent_pool = (sorted(population, key=plan_cost)[:population_size // 2]
                       if selection_method == "best_half" else population)
        new_population = [best]  # Элитизм: лучший план никогда не теряется.
        crossovers = mutations = repairs = 0
        while len(new_population) < population_size:
            first, second = select(parent_pool), select(parent_pool)
            preferred = tuple(first[i] if rng.random() < 0.5 else second[i] for i in range(n))
            crossovers += 1
            if feasible(preferred):
                child = preferred
            else:
                child = construct(preferred)
                if child is not None:
                    repairs += 1
                else:
                    child = min((first, second), key=plan_cost)
            if rng.random() < 0.6:
                changed = mutate(child)
                if changed != child:
                    mutations += 1
                    child = changed
            new_population.append(child)
        population = new_population
        generation_best = min(population, key=plan_cost)
        if plan_cost(generation_best) < plan_cost(best):
            best = generation_best
        record(generation, crossovers, mutations, repairs)

    assignment = {container["id"]: sites[best[i]]["id"] for i, container in enumerate(containers)}
    final_check = evaluate({**task, "assignment": assignment})
    if not final_check["valid"] or final_check["totalCost"] != plan_cost(best):
        raise RuntimeError("Ошибка внутренней проверки генетического плана.")
    return {"method": "genetic", "implemented": True, "status": "found",
            "provenOptimal": False, "message": "Найден допустимый план; оптимальность не доказана.",
            "bestCost": final_check["totalCost"], "bestAssignment": assignment,
            "history": history, "generationsRun": generations,
            "populationSize": population_size, "seed": seed,
            "selectionMethod": selection_method}
