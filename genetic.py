"""Генетический поиск допустимого размещения без сторонних библиотек."""

import random

from model import evaluate, integer_option, placement_options, verified_assignment


def solve_genetic(task, options=None):
    """Ищет допустимый план; история хранит лучший план после каждого поколения."""
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

    def construct(preferred=None, max_nodes=5000):
        """Собирает допустимый план, пробуя другие площадки при тупике."""
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
            if preferred is not None and preferred[i] in choices and rng.random() < 0.7:
                choices.remove(preferred[i])
                choices.insert(0, preferred[i])
            options_by_container.append(choices)

        visited = 0

        def fill(depth):
            nonlocal visited
            if depth == n:
                return True
            i = order[depth]
            for j in options_by_container[depth]:
                visited += 1
                if visited > max_nodes:
                    return False
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

        return tuple(plan) if fill(0) else None

    def mutate(plan):
        """Пробует выбранный тип мутации и возвращает допустимый вариант."""
        for _ in range(12):
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
            if feasible(changed):
                return tuple(changed)
        return plan

    current = task["assignment"]
    initial = tuple(site_index.get(current.get(c["id"]), -1) for c in containers)
    population = [initial] if feasible(initial) else []
    for _ in range(population_size * 4):
        if len(population) >= population_size:
            break
        candidate = construct(max_nodes=50_000)
        if candidate is not None and candidate not in population:
            population.append(candidate)
    if not population:
        return {"method": "genetic", "implemented": True, "status": "not_found",
                "provenOptimal": False, "message": "Допустимый план не найден. Это не доказывает, что его нет.",
                "history": [], "generationsRun": 0, "populationSize": population_size,
                "seed": seed, "selectionMethod": selection_method,
                "mutationEnabled": mutation_enabled, "mutationType": mutation_type,
                "mutationProbability": mutation_probability}
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
            if (mutation_enabled and mutation_probability > 0
                    and rng.random() < mutation_probability / 100):
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

    best_cost = plan_cost(best)
    assignment = verified_assignment(task, best, best_cost)
    return {"method": "genetic", "implemented": True, "status": "found",
            "provenOptimal": False, "message": "Найден допустимый план. Минимальная стоимость не подтверждена.",
            "bestCost": best_cost, "bestAssignment": assignment,
            "history": history, "generationsRun": generations,
            "populationSize": population_size, "seed": seed,
            "selectionMethod": selection_method,
            "mutationEnabled": mutation_enabled, "mutationType": mutation_type,
            "mutationProbability": mutation_probability}
