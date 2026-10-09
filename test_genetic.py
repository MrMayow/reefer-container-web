"""Проверки генетического поиска и его истории."""

import random
import unittest
from unittest.mock import Mock, patch

from genetic import solve_genetic
from model import evaluate, generate_example


class GeneticTests(unittest.TestCase):
    def test_tight_sites_still_create_diverse_population(self):
        task = generate_example(13, 5, 26)
        original_cost = evaluate(task)["totalCost"]
        answer = solve_genetic(task, {"generations": 60, "populationSize": 36,
                                      "seed": 26, "selectionMethod": "best_half",
                                      "mutationType": "move", "mutationProbability": 60})
        self.assertGreater(answer["history"][0]["distinctPlans"], 1)
        self.assertLess(answer["bestCost"], original_cost)
        self.assertLessEqual(answer["bestCost"], answer["history"][0]["bestCost"])
        self.assertEqual(answer["history"][0]["populationCount"], 36)
        self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])

    def test_result_and_each_shown_stage_are_feasible(self):
        task = generate_example(12, 3, 26)
        original_cost = evaluate(task)["totalCost"]
        for method in ("tournament", "best_half"):
            with self.subTest(method=method):
                answer = solve_genetic(task, {"generations": 20, "populationSize": 24,
                                              "seed": 7, "selectionMethod": method})
                self.assertEqual(answer["status"], "found")
                self.assertEqual(answer["selectionMethod"], method)
                self.assertFalse(answer["provenOptimal"])
                self.assertEqual(len(answer["history"]), 21)
                self.assertLessEqual(answer["bestCost"], original_cost)
                costs = []
                for record in answer["history"]:
                    self.assertEqual(record["populationCount"], record["distinctPlans"])
                    assignment = {container["id"]: task["sites"][record["bestChromosome"][i]]["id"]
                                  for i, container in enumerate(task["containers"])}
                    checked = evaluate({**task, "assignment": assignment})
                    self.assertTrue(checked["valid"])
                    self.assertEqual(checked["totalCost"], record["bestCost"])
                    costs.append(record["bestCost"])
                self.assertEqual(costs, sorted(costs, reverse=True))
                self.assertEqual(costs[-1], answer["bestCost"])
                self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])

    def test_single_feasible_plan_is_not_copied_to_fill_population(self):
        task = generate_example(3, 1, 26)
        for selection in ("tournament", "best_half"):
            with self.subTest(selection=selection):
                answer = solve_genetic(task, {"generations": 4, "populationSize": 8,
                                              "selectionMethod": selection})
                self.assertEqual(len(answer["history"]), 5)
                self.assertTrue(all(stage["populationCount"] == stage["distinctPlans"] == 1
                                    for stage in answer["history"]))
                self.assertEqual(answer["initialAttempts"], 1)
                self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])

    def test_repair_and_mutation_keep_generations_unique(self):
        task = generate_example(13, 5, 26)
        for selection in ("tournament", "best_half"):
            with self.subTest(selection=selection):
                answer = solve_genetic(task, {"generations": 8, "populationSize": 24,
                                              "selectionMethod": selection,
                                              "mutationProbability": 100})
                self.assertGreater(sum(stage["repairs"] for stage in answer["history"]), 0)
                self.assertGreater(sum(stage["mutations"] for stage in answer["history"]), 0)
                self.assertTrue(all(stage["populationCount"] == stage["distinctPlans"]
                                    for stage in answer["history"]))

    def test_two_feasible_plans_work_with_both_selection_methods(self):
        task = generate_example(1, 2, 3)
        container = task["containers"][0]
        task["sites"][1]["massLimit"] = container["weight"]
        task["sites"][1]["powerLimit"] = container["power"]
        task["limitHours"] = 100
        for selection in ("tournament", "best_half"):
            with self.subTest(selection=selection):
                answer = solve_genetic(task, {"generations": 4, "populationSize": 8,
                                              "selectionMethod": selection, "mutationType": "move",
                                              "mutationProbability": 100})
                self.assertTrue(all(stage["populationCount"] == stage["distinctPlans"] == 2
                                    for stage in answer["history"]))

    def test_failed_repair_immediately_takes_cheapest_unused_reserve(self):
        task = generate_example(13, 5, 26)
        unavailable = 0
        for selection in ("tournament", "best_half"):
            with self.subTest(selection=selection):
                answer = solve_genetic(task, {"generations": 8, "populationSize": 24,
                                              "selectionMethod": selection, "mutationProbability": 100})
                discarded = set()
                reserves_from_pool = 0
                for before, stage in zip(answer["history"], answer["history"][1:]):
                    ordered = sorted(before["population"], key=lambda i: answer["plans"][i]["cost"])
                    used, reserved, added = set(), set(), []
                    for i, event in enumerate(stage["events"]):
                        if event["kind"] == "crossover":
                            self.assertFalse(reserved.intersection(event["parents"]))
                            for group in event["participants"]:
                                self.assertFalse(reserved.intersection(group))
                            used.update(event["parents"])
                        if "reserve" in event:
                            self.assertIsNone(event["repaired"])
                            candidates = [p for p in ordered if p not in used and p not in added]
                            expected = candidates[0] if candidates else None
                            self.assertEqual(event["reserve"], expected)
                            if expected is None:
                                unavailable += 1
                            else:
                                following = stage["events"][i + 1]
                                self.assertEqual(following["kind"], "reserve")
                                self.assertEqual(following["result"], expected)
                        if event["kind"] == "reserve":
                            self.assertEqual(stage["events"][i - 1]["reserve"], event["result"])
                            self.assertNotIn(event["result"], used)
                            reserved.add(event["result"])
                            reserves_from_pool += event["result"] in stage["parentPool"]
                        if event["status"] == "accepted":
                            self.assertNotIn(event["result"], added)
                            self.assertNotIn(event["result"], discarded)
                            added.append(event["result"])
                    self.assertEqual(added, stage["population"])
                    self.assertEqual(stage["immediateReserves"], len(reserved))
                    self.assertEqual(stage["carriedOver"], sum(e["kind"] in ("reserve", "carry")
                                                              for e in stage["events"]))
                    self.assertFalse(reserved.intersection(used))
                    discarded.update(stage["discarded"])
                # Проверено удаление резерва и из турниров, и из лучшей половины.
                self.assertGreater(reserves_from_pool, 0)
        # Когда резерв исчерпан, алгоритм продолжает попытки без копирования планов.
        self.assertGreater(unavailable, 0)

    def test_same_seed_repeats_search(self):
        task = generate_example(10, 3, 9)
        for method in ("tournament", "best_half"):
            with self.subTest(method=method):
                options = {"generations": 8, "populationSize": 12,
                           "seed": 42, "selectionMethod": method}
                self.assertEqual(solve_genetic(task, options), solve_genetic(task, options))

    def test_initial_search_finds_all_plans_despite_repeated_first_choices(self):
        task = generate_example(3, 2, 26)
        for container in task["containers"]:
            container.update(weight=1, power=1, storage=1)
        for j, site in enumerate(task["sites"]):
            site.update(places=3, massLimit=10, powerLimit=10,
                        storageRate=j + 1, travelTime=0, travelRate=0)
        rng = Mock(wraps=random.Random(26))
        rng.random.return_value = 0.0  # Сначала всегда пробуется дешёвая площадка A.
        with patch("genetic.random.Random", return_value=rng):
            answer = solve_genetic(task, {"generations": 1, "populationSize": 12,
                                          "mutationEnabled": False})
        initial = answer["history"][0]
        self.assertEqual(initial["populationCount"], 8)  # Всего 2 ** 3 размещений.
        self.assertEqual(initial["distinctPlans"], 8)
        self.assertEqual(answer["initialAttempts"], 8)
        self.assertGreater(answer["initialNodesVisited"], 0)

    def test_best_half_can_create_more_children_than_parent_count(self):
        task = generate_example(6, 3, 26)
        for site in task["sites"]:
            site.update(places=6, massLimit=1000, powerLimit=1000)
        task["limitHours"] = 100
        answer = solve_genetic(task, {"generations": 1, "populationSize": 12,
                                      "selectionMethod": "best_half", "mutationEnabled": False})
        initial, last = answer["history"]
        self.assertEqual(initial["populationCount"], 12)
        self.assertEqual(last["populationCount"], 12)
        self.assertLessEqual(last["parentsUsed"], 6)
        self.assertGreater(last["crossovers"], 6)
        self.assertEqual(last["carriedOver"], 0)

    def test_fill_skips_used_parent_even_when_its_child_was_a_duplicate(self):
        task = generate_example(2, 2, 26)
        for container in task["containers"]:
            container.update(weight=1, power=1, storage=1)
        for j, site in enumerate(task["sites"]):
            site.update(places=2, massLimit=10, powerLimit=10,
                        storageRate=j + 1, travelTime=0, travelRate=0)
        task["assignment"] = {container["id"]: "A" for container in task["containers"]}
        rng = Mock(wraps=random.Random(26))
        parent_draws = []

        def tournament(pool, count):
            ordered = sorted(pool, key=lambda plan: (sum(plan), plan))
            offset = len(parent_draws) % 2
            participants = ordered[offset:offset + count]
            parent_draws.append(participants[0])
            rng.random.return_value = 0.0  # Каждый потомок повторяет первого родителя.
            return participants

        rng.sample.side_effect = tournament
        with patch("genetic.random.Random", return_value=rng):
            answer = solve_genetic(task, {"generations": 3, "populationSize": 4,
                                          "mutationEnabled": False})
        self.assertEqual(answer["history"][0]["populationCount"], 4)
        last = answer["history"][1]
        self.assertEqual(last["parentsUsed"], 2)
        self.assertEqual(last["carriedOver"], 2)
        self.assertEqual(last["populationCount"], 3)
        self.assertEqual(last["distinctPlans"], 3)
        # После выпадения планов добор не возвращает их в следующих поколениях.
        self.assertEqual([stage["populationCount"] for stage in answer["history"]], [4, 3, 2, 1])
        discarded = set()
        for stage in answer["history"]:
            self.assertFalse(discarded.intersection(stage["population"]))
            discarded.update(stage["discarded"])
            self.assertEqual(len(discarded), stage["discardedCount"])

    def test_mutation_can_be_disabled_or_limited_to_one_type(self):
        task = generate_example(1, 2, 3)
        container = task["containers"][0]
        task["sites"][1]["massLimit"] = container["weight"]
        task["sites"][1]["powerLimit"] = container["power"]
        task["limitHours"] = 100
        options = {"generations": 8, "populationSize": 8, "seed": 7}

        disabled = solve_genetic(task, {**options, "mutationEnabled": False})
        moved = solve_genetic(task, {**options, "mutationType": "move"})
        swapped = solve_genetic(task, {**options, "mutationType": "swap"})
        self.assertFalse(disabled["mutationEnabled"])
        self.assertEqual(disabled["mutationType"], "swap")
        self.assertTrue(moved["mutationEnabled"])
        self.assertEqual(moved["mutationType"], "move")
        self.assertEqual(swapped["mutationType"], "swap")
        self.assertEqual(sum(stage["mutations"] for stage in disabled["history"]), 0)
        self.assertGreater(sum(stage["mutations"] for stage in moved["history"]), 0)
        self.assertEqual(sum(stage["mutations"] for stage in swapped["history"]), 0)

        many = generate_example(12, 3, 26)
        swapped = solve_genetic(many, {**options, "mutationType": "swap"})
        self.assertGreater(sum(stage["mutations"] for stage in swapped["history"]), 0)
        self.assertTrue(evaluate({**many, "assignment": swapped["bestAssignment"]})["valid"])

    def test_mutation_probability_limits(self):
        task = generate_example(1, 2, 3)
        container = task["containers"][0]
        task["sites"][1]["massLimit"] = container["weight"]
        task["sites"][1]["powerLimit"] = container["power"]
        task["limitHours"] = 100
        options = {"generations": 8, "populationSize": 8, "seed": 7,
                   "mutationType": "move"}
        never = solve_genetic(task, {**options, "mutationProbability": 0})
        always = solve_genetic(task, {**options, "mutationProbability": 100})
        self.assertEqual(never["mutationProbability"], 0)
        self.assertEqual(always["mutationProbability"], 100)
        self.assertEqual(sum(stage["mutations"] for stage in never["history"]), 0)
        self.assertGreater(sum(stage["mutations"] for stage in always["history"]), 0)
        disabled = solve_genetic(task, {**options, "mutationEnabled": False})
        # Поиск одинаковый; подробный журнал различает выключенные мутации и вероятность 0%.
        self.assertEqual([{k: v for k, v in stage.items() if k != "events"} for stage in never["history"]],
                         [{k: v for k, v in stage.items() if k != "events"} for stage in disabled["history"]])
        self.assertEqual(never["plans"], disabled["plans"])
        self.assertEqual(solve_genetic(task, options),
                         solve_genetic(task, {**options, "mutationProbability": 60}))

    def test_no_plan_found_is_not_a_proof(self):
        task = generate_example(2, 1, 3)
        task["sites"][0]["places"] = 0
        answer = solve_genetic(task, {"generations": 3, "populationSize": 4})
        self.assertEqual(answer["status"], "not_found")
        self.assertFalse(answer["provenOptimal"])
        self.assertNotIn("bestAssignment", answer)

    def test_discarded_plans_do_not_return_through_repair_mutation_or_fill(self):
        task = generate_example(13, 5, 26)
        for selection in ("tournament", "best_half"):
            with self.subTest(selection=selection):
                answer = solve_genetic(task, {"generations": 6, "populationSize": 16,
                                              "selectionMethod": selection, "mutationProbability": 100})
                discarded = set()
                repairs = 0
                for stage in answer["history"]:
                    self.assertFalse(discarded.intersection(stage["population"]))
                    for event in stage["events"]:
                        if event.get("repaired") is not None:
                            repairs += 1
                            self.assertNotIn(event["repaired"], discarded)
                        if event["status"] == "accepted":
                            self.assertNotIn(event["result"], discarded)
                    discarded.update(stage["discarded"])
                    self.assertEqual(len(discarded), stage["discardedCount"])
                self.assertGreater(repairs, 0)
                self.assertGreater(len(discarded), 0)

    def test_generation_trace_matches_actual_population_and_parent_selection(self):
        task = generate_example(12, 3, 26)
        answer = solve_genetic(task, {"generations": 4, "populationSize": 12,
                                      "mutationProbability": 100})
        plans = answer["plans"]
        self.assertEqual(len(plans), len({tuple(plan["chromosome"]) for plan in plans}))
        for stage in answer["history"]:
            accepted = []
            crossovers = repairs = mutations = 0
            for event in stage["events"]:
                if event["kind"] == "crossover":
                    crossovers += 1
                    for parent, participants in zip(event["parents"], event["participants"]):
                        self.assertEqual(len(participants), len(set(participants)))
                        self.assertTrue(set(participants).issubset(stage["parentPool"]))
                        self.assertIn(parent, participants)
                        self.assertEqual(plans[parent]["cost"], min(plans[p]["cost"] for p in participants))
                    first, second = [plans[p]["chromosome"] for p in event["parents"]]
                    self.assertTrue(all(j in (first[i], second[i]) for i, j in enumerate(plans[event["crossed"]]["chromosome"])))
                    repairs += event.get("repaired") is not None
                    mutations += event.get("mutation") == "changed"
                if event["status"] == "duplicate":
                    self.assertIn(event["result"], accepted)
                if event["status"] == "accepted":
                    self.assertNotIn(event["result"], accepted)
                    accepted.append(event["result"])
            self.assertEqual(accepted, stage["population"])
            self.assertEqual((crossovers, repairs, mutations), (stage["crossovers"], stage["repairs"], stage["mutations"]))
            for id in stage["population"]:
                assignment = {c["id"]: task["sites"][plans[id]["chromosome"][i]]["id"]
                              for i, c in enumerate(task["containers"])}
                checked = evaluate({**task, "assignment": assignment})
                self.assertTrue(checked["valid"])
                self.assertEqual(checked["totalCost"], plans[id]["cost"])

    def test_fractional_or_excessive_settings_are_rejected(self):
        task = generate_example(2, 1, 3)
        for options in ({"generations": 1.5}, {"populationSize": 1000},
                        {"seed": -1}, {"selectionMethod": "unknown"},
                        {"mutationEnabled": 1}, {"mutationType": "unknown"},
                        {"mutationProbability": -1}, {"mutationProbability": 101},
                        {"mutationProbability": 1.5}, {"mutationProbability": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                solve_genetic(task, options)


if __name__ == "__main__":
    unittest.main()
