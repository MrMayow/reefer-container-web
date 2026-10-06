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
        self.assertLess(answer["bestCost"], answer["history"][0]["bestCost"])
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

    def test_same_seed_repeats_search(self):
        task = generate_example(10, 3, 9)
        for method in ("tournament", "best_half"):
            with self.subTest(method=method):
                options = {"generations": 8, "populationSize": 12,
                           "seed": 42, "selectionMethod": method}
                self.assertEqual(solve_genetic(task, options), solve_genetic(task, options))

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
            answer = solve_genetic(task, {"generations": 1, "populationSize": 4,
                                          "mutationEnabled": False})
        self.assertEqual(answer["history"][0]["populationCount"], 4)
        last = answer["history"][-1]
        self.assertEqual(last["parentsUsed"], 2)
        self.assertEqual(last["carriedOver"], 2)
        self.assertEqual(last["populationCount"], 3)
        self.assertEqual(last["distinctPlans"], 3)

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
        self.assertEqual(never["history"], disabled["history"])
        self.assertEqual(solve_genetic(task, options),
                         solve_genetic(task, {**options, "mutationProbability": 60}))

    def test_no_plan_found_is_not_a_proof(self):
        task = generate_example(2, 1, 3)
        task["sites"][0]["places"] = 0
        answer = solve_genetic(task, {"generations": 3, "populationSize": 4})
        self.assertEqual(answer["status"], "not_found")
        self.assertFalse(answer["provenOptimal"])
        self.assertNotIn("bestAssignment", answer)

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
