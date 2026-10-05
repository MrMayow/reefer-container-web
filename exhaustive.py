"""Полный перебор назначений контейнеров без отсечения ветвей."""

import os
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from itertools import product
from time import perf_counter

from model import evaluate, integer_option, placement_options, verified_assignment


def check_chunk(prefix, suffix_length, m, containers, sites, allowed, costs):
    """Проверяет группу назначений, начинающихся с одного префикса."""
    checked = valid = 0
    best_cost = best = None
    for suffix in product(range(m), repeat=suffix_length):
        plan = prefix + suffix if prefix else suffix
        checked += 1
        counts = [0] * m
        weights = [0] * m
        powers = [0] * m
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
                break
            cost += costs[i][j]
        else:
            valid += 1
            if best_cost is None or cost < best_cost:
                best_cost, best = cost, plan
    return checked, valid, best_cost, best


def solve_exhaustive(task, options=None, progress=None):
    """Проверяет все назначения; несколько процессов используют разные группы."""
    evaluate(task)
    if options is None:
        options = {}
    if not isinstance(options, dict):
        raise ValueError("Параметры метода должны быть объектом JSON.")
    containers = task["containers"]
    sites = task["sites"]
    n, m = len(containers), len(sites)
    total = m ** n
    available = os.cpu_count() or 1
    requested = integer_option(options, "workers", 0, 0, available)
    workers = requested or (1 if total < 1_000_000 else min(available, max(2, total // 250_000)))
    suffix_length = 0
    chunk_size = 8192 if workers == 1 else 100_000
    while suffix_length < n and m ** (suffix_length + 1) <= chunk_size:
        suffix_length += 1
    workers = min(workers, m ** (n - suffix_length))
    prefixes = product(range(m), repeat=n - suffix_length)
    choices, costs = placement_options(task)
    args = (suffix_length, m, containers, sites, [set(row) for row in choices], costs)

    checked_count = valid_count = 0
    best_cost = None
    best = None
    history = []
    checkpoint = max(1, total // 60)
    next_checkpoint = checkpoint
    started_at = last_report = perf_counter()

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

    def add_result(result):
        nonlocal checked_count, valid_count, best_cost, best, last_report, next_checkpoint
        checked, valid, cost, plan = result
        checked_count += checked
        valid_count += valid
        if cost is not None and (best_cost is None or cost < best_cost):
            best_cost, best = cost, plan
            record("Найден более дешёвый допустимый план")
        elif cost == best_cost and plan is not None and plan < best:
            best = plan  # Равные минимумы выбираются одинаково при любом порядке процессов.
        if checked_count >= next_checkpoint:
            record("Промежуточный этап")
            next_checkpoint = checked_count + checkpoint
        now = perf_counter()
        if progress and now - last_report >= 0.5:
            progress({"checkedCount": checked_count, "validCount": valid_count,
                      "bestCost": best_cost, "totalCombinations": str(total),
                      "elapsedSeconds": now - started_at, "workers": workers})
            last_report = now

    record("Начало перебора")
    if progress:
        progress({"checkedCount": 0, "validCount": 0, "bestCost": None,
                  "totalCombinations": str(total), "elapsedSeconds": 0,
                  "workers": workers})

    if workers == 1:
        for prefix in prefixes:
            add_result(check_chunk(prefix, *args))
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            pending = set()
            for prefix in prefixes:
                pending.add(pool.submit(check_chunk, prefix, *args))
                if len(pending) < 2 * workers:
                    continue
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    add_result(future.result())
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    add_result(future.result())

    if best is not None:
        status = "optimal"
        message = "Все назначения проверены."
    else:
        status = "infeasible"
        message = "Все назначения проверены: допустимого размещения нет."
    record(message)

    answer = {"method": "exhaustive", "implemented": True, "status": status,
              "message": message, "provenOptimal": status == "optimal",
              "provenInfeasible": status == "infeasible",
              "totalCombinations": str(total), "workers": workers,
              "checkedCount": checked_count, "validCount": valid_count,
              "invalidCount": checked_count - valid_count, "history": history}
    if best is not None:
        assignment = verified_assignment(task, best, best_cost)
        answer["bestCost"] = best_cost
        answer["bestAssignment"] = assignment
    answer["elapsedSeconds"] = perf_counter() - started_at
    return answer
