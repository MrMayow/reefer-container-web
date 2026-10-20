"""Данные, проверка плана и расчёт стоимости размещения."""

import random


def generate_example(container_count=12, site_count=3, seed=26):
    """Создаёт правдоподобный пример и заведомо допустимое начальное назначение."""
    if type(container_count) is not int or not 1 <= container_count <= 80:
        raise ValueError("Число контейнеров должно быть от 1 до 80.")
    if type(site_count) is not int or not 1 <= site_count <= 10:
        raise ValueError("Число площадок должно быть от 1 до 10.")
    if type(seed) is not int or not 0 <= seed <= 999999:
        raise ValueError("Зерно генерации должно быть от 0 до 999999.")

    rng = random.Random(seed)
    site_ids = [chr(65 + index) for index in range(site_count)]
    sites = []
    for index, site_id in enumerate(site_ids):
        sites.append({
            "id": site_id,
            "places": 0,
            "massLimit": 0,
            "powerLimit": 0,
            "storageRate": 95 + index * 26,
            "travelTime": index + 1,
            "travelRate": 420 + index * 95,
        })

    containers = []
    assignment = {}
    for index in range(container_count):
        container = {
            "id": f"К{index + 1:02d}",
            "weight": rng.randint(12, 29),
            "power": rng.randint(4, 9),
            "storage": rng.randint(9, 27),
        }
        containers.append(container)
        site_index = index % site_count
        assignment[container["id"]] = site_ids[site_index]
        sites[site_index]["places"] += 1
        sites[site_index]["massLimit"] += container["weight"]
        sites[site_index]["powerLimit"] += container["power"]

    for site in sites:
        site["places"] += 1
        site["massLimit"] += max(2, site["massLimit"] // 10)
        site["powerLimit"] += max(1, site["powerLimit"] // 10)

    travel_by_site = {site["id"]: site["travelTime"] for site in sites}
    longest = max(container["storage"] + travel_by_site[assignment[container["id"]]]
                  for container in containers)
    return {
        "containers": containers,
        "sites": sites,
        "assignment": assignment,
        "limitHours": max(30, longest),
    }


def _number(value, label):
    if type(value) is not int or value < 0 or value > 1_000_000:
        raise ValueError(f"{label}: требуется целое число от 0 до 1000000.")
    return value


def integer_option(options, name, default, minimum, maximum):
    value = options.get(name, default)
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name}: требуется целое число от {minimum} до {maximum}.")
    return value


def cost_parts(container, site):
    """Возвращает стоимость хранения и перевозки одного контейнера."""
    storage = container["storage"] * site["storageRate"]
    travel = site["travelTime"] * site["travelRate"]
    return storage, travel


def placement_options(task):
    """Готовит подходящие площадки и стоимость для каждого контейнера."""
    choices, costs = [], []
    for container in task["containers"]:
        choices.append([j for j, site in enumerate(task["sites"])
                        if container["storage"] + site["travelTime"] <= task["limitHours"]
                        and site["places"] >= 1
                        and container["weight"] <= site["massLimit"]
                        and container["power"] <= site["powerLimit"]])
        costs.append([sum(cost_parts(container, site))
                      for site in task["sites"]])
    return choices, costs


def evaluate(data):
    """Возвращает стоимость и нарушения; недопустимый план не выдаётся за решение."""
    if not isinstance(data, dict):
        raise ValueError("Данные задачи должны быть объектом JSON.")
    containers = data.get("containers")
    sites = data.get("sites")
    assignment = data.get("assignment")
    if not isinstance(containers, list) or not 1 <= len(containers) <= 80:
        raise ValueError("Нужно от 1 до 80 контейнеров.")
    if not isinstance(sites, list) or not 1 <= len(sites) <= 10:
        raise ValueError("Нужно от 1 до 10 площадок.")
    if not isinstance(assignment, dict):
        raise ValueError("Назначение должно быть объектом JSON.")
    limit = _number(data.get("limitHours"), "Срок перевозки и хранения")

    container_ids = set()
    site_ids = set()
    for container in containers:
        if not isinstance(container, dict):
            raise ValueError("Неверная запись контейнера.")
        cid = container.get("id")
        if not isinstance(cid, str) or not cid.strip() or cid in container_ids:
            raise ValueError("Имена контейнеров должны быть непустыми и уникальными.")
        container_ids.add(cid)
        for key, title in (("weight", "Масса"), ("power", "Мощность"), ("storage", "Время хранения")):
            _number(container.get(key), f"{title} {cid}")
    for site in sites:
        if not isinstance(site, dict):
            raise ValueError("Неверная запись площадки.")
        sid = site.get("id")
        if not isinstance(sid, str) or not sid.strip() or sid in site_ids:
            raise ValueError("Имена площадок должны быть непустыми и уникальными.")
        site_ids.add(sid)
        for key, title in (("places", "Места"), ("massLimit", "Предел массы"),
                           ("powerLimit", "Предел мощности"), ("storageRate", "Тариф хранения"),
                           ("travelTime", "Время перевозки"), ("travelRate", "Тариф перевозки")):
            _number(site.get(key), f"{title} {sid}")
    if any(cid not in container_ids for cid in assignment):
        raise ValueError("Назначение ссылается на неизвестный контейнер.")

    loads = {site["id"]: {"id": site["id"], "count": 0, "weight": 0,
                          "power": 0, "cost": 0, "issues": []} for site in sites}
    site_by_id = {site["id"]: site for site in sites}
    rows = []
    issues = []
    total = 0
    for container in containers:
        cid = container["id"]
        sid = assignment.get(cid)
        row = {"id": cid, "site": sid, "storageCost": 0,
               "travelCost": 0, "cost": 0, "issues": []}
        if sid is None or sid == "":
            row["issues"].append("Не назначен на площадку")
        elif sid not in site_by_id:
            row["issues"].append("Указана неизвестная площадка")
        else:
            site = site_by_id[sid]
            load = loads[sid]
            load["count"] += 1
            load["weight"] += container["weight"]
            load["power"] += container["power"]
            row["storageCost"], row["travelCost"] = cost_parts(container, site)
            row["cost"] = row["storageCost"] + row["travelCost"]
            load["cost"] += row["cost"]
            total += row["cost"]
            if site["travelTime"] + container["storage"] > limit:
                row["issues"].append("Превышен срок перевозки и хранения")
        for issue in row["issues"]:
            issues.append(f"{cid}: {issue}.")
        rows.append(row)

    for site in sites:
        load = loads[site["id"]]
        for used, maximum, label in ((load["count"], site["places"], "число мест"),
                                     (load["weight"], site["massLimit"], "масса"),
                                     (load["power"], site["powerLimit"], "мощность")):
            if used > maximum:
                load["issues"].append(f"Превышен лимит: {label}")
        for issue in load["issues"]:
            issues.append(f"Площадка {site['id']}: {issue}.")

    return {"valid": not issues, "totalCost": total, "issues": issues,
            "loads": list(loads.values()), "rows": rows,
            "provenOptimal": False, "method": "manual"}


def verified_assignment(task, plan, cost):
    """Переводит индексы площадок в имена и проверяет найденный план."""
    assignment = {container["id"]: task["sites"][plan[i]]["id"]
                  for i, container in enumerate(task["containers"])}
    result = evaluate({**task, "assignment": assignment})
    if not result["valid"] or result["totalCost"] != cost:
        raise RuntimeError("Ошибка внутренней проверки найденного плана.")
    return assignment
