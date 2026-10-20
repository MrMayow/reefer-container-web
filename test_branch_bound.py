"""Проверка минимальной стоимости, ограниченного поиска и этапов."""

from itertools import product
import unittest

from branch_bound import solve_branch_bound
from model import evaluate, generate_example


class BranchBoundTests(unittest.TestCase):
    def test_large_case_improves_current_plan_within_default_limit(self):
        task = generate_example(25, 5, 26)
        initial_cost = evaluate(task)["totalCost"]
        answer = solve_branch_bound(task)
        self.assertLess(answer["bestCost"], initial_cost)
        self.assertGreater(answer["improvements"], 0)
        self.assertEqual(answer["status"], "limit_with_plan")
        self.assertFalse(answer["provenOptimal"])
        self.assertEqual(answer["nodesVisited"], 100_000)
        self.assertEqual(answer["history"][0]["improvements"], 0)
        improvements = [s["improvements"] for s in answer["history"]]
        self.assertEqual(improvements, sorted(improvements))
        self.assertEqual(improvements[-1], answer["improvements"])
        self.assertEqual(answer["improvements"], sum(s["event"] == "Найден лучший план"
                                                   for s in answer["history"]))
        self.assertEqual(answer["history"][-1]["bestCost"], answer["bestCost"])
        self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])

    def test_flat_history_is_correct_when_starting_plan_already_has_minimum_cost(self):
        task = generate_example(5, 3, 26)
        best = solve_branch_bound(task)
        task["assignment"] = best["bestAssignment"]
        answer = solve_branch_bound(task)
        self.assertTrue(answer["provenOptimal"])
        self.assertEqual(answer["improvements"], 0)
        self.assertEqual({s["bestCost"] for s in answer["history"]}, {best["bestCost"]})

    def test_returns_to_another_branch_when_greedy_choice_is_more_expensive(self):
        task = {"containers": [{"id": "К01", "weight": 1, "power": 1, "storage": 1},
                               {"id": "К02", "weight": 1, "power": 1, "storage": 10}],
                "sites": [{"id": "A", "places": 1, "massLimit": 10, "powerLimit": 10,
                           "storageRate": 1, "travelTime": 0, "travelRate": 0},
                          {"id": "B", "places": 1, "massLimit": 10, "powerLimit": 10,
                           "storageRate": 10, "travelTime": 0, "travelRate": 0}],
                "assignment": {"К01": "A", "К02": "B"},
                "limitHours": 20}
        self.assertEqual(evaluate(task)["totalCost"], 101)
        answer = solve_branch_bound(task)
        self.assertEqual(answer["bestCost"], 20)
        self.assertEqual(answer["bestAssignment"], {"К01": "B", "К02": "A"})
        self.assertTrue(answer["provenOptimal"])
        self.assertEqual([node["site"] for node in answer["tree"] if node["depth"] == 1], ["A", "B"])
        self.assertEqual({node["status"] for node in answer["tree"]}, {"branch", "bound", "plan", "capacity"})

    def test_tree_bounds_and_resource_pruning_are_safe(self):
        task = generate_example(4, 3, 7)
        answer = solve_branch_bound(task)
        tree = answer["tree"]
        self.assertFalse(answer["treeTruncated"])
        for index, node in enumerate(tree):
            partial = {}
            ancestor = index
            while ancestor is not None:
                current = tree[ancestor]
                if current["container"]:
                    partial[current["container"]] = current["site"]
                ancestor = current["parent"]
            self.assertEqual(evaluate({**task, "assignment": partial})["totalCost"], node["cost"])
            if node["parent"] is not None:
                self.assertLess(node["parent"], index)
                self.assertEqual(node["depth"], tree[node["parent"]]["depth"] + 1)
            remaining = [c["id"] for c in task["containers"] if c["id"] not in partial]
            completions = []
            for sites in product((site["id"] for site in task["sites"]), repeat=len(remaining)):
                checked = evaluate({**task, "assignment": {**partial, **dict(zip(remaining, sites))}})
                if checked["valid"]:
                    completions.append(checked["totalCost"])
            if completions and node["lowerBound"] is not None:
                self.assertLessEqual(node["lowerBound"], min(completions))
            if node["status"] == "bound":
                self.assertGreaterEqual(node["lowerBound"], node["bestCost"])
            if node["status"] == "capacity":
                self.assertFalse(completions)

    def test_tree_size_does_not_stop_search(self):
        answer = solve_branch_bound(generate_example(13, 5, 26))
        self.assertTrue(answer["treeTruncated"])
        self.assertEqual(len(answer["tree"]), answer["treeLimit"])
        self.assertGreater(answer["nodesVisited"], answer["treeLimit"])
        self.assertTrue(answer["provenOptimal"])
        self.assertEqual(answer["bestCost"], 53637)

    def test_matches_exhaustive_search(self):
        for seed in (7, 26):
            with self.subTest(seed=seed):
                task = generate_example(5, 3, seed)
                exact = solve_branch_bound(task, {"nodeLimit": 10000})
                brute_costs = []
                for sites in product((site["id"] for site in task["sites"]), repeat=5):
                    assignment = dict(zip((c["id"] for c in task["containers"]), sites))
                    checked = evaluate({**task, "assignment": assignment})
                    if checked["valid"]:
                        brute_costs.append(checked["totalCost"])
                self.assertEqual(exact["status"], "optimal")
                self.assertTrue(exact["provenOptimal"])
                self.assertEqual(exact["bestCost"], min(brute_costs))
                self.assertLessEqual(exact["rootLowerBound"], exact["bestCost"])

    def test_every_reported_incumbent_is_valid(self):
        task = generate_example(12, 3, 26)
        answer = solve_branch_bound(task)
        self.assertEqual(answer["status"], "optimal")
        self.assertEqual(answer["history"][-1]["nodesVisited"], answer["nodesVisited"])
        costs = []
        for stage in answer["history"]:
            chromosome = stage["bestChromosome"]
            if chromosome is None:
                continue
            assignment = {container["id"]: task["sites"][chromosome[i]]["id"]
                          for i, container in enumerate(task["containers"])}
            checked = evaluate({**task, "assignment": assignment})
            self.assertTrue(checked["valid"])
            self.assertEqual(stage["bestCost"], checked["totalCost"])
            costs.append(stage["bestCost"])
        self.assertEqual(costs, sorted(costs, reverse=True))
        self.assertEqual(costs[-1], answer["bestCost"])

    def test_search_without_initial_plan_matches_independent_exhaustive_search(self):
        for seed in (3, 7, 26, 42):
            with self.subTest(seed=seed):
                task = generate_example(5, 3, seed)
                task["assignment"] = {}
                costs = []
                for sites in product((site["id"] for site in task["sites"]), repeat=5):
                    assignment = dict(zip((c["id"] for c in task["containers"]), sites))
                    checked = evaluate({**task, "assignment": assignment})
                    if checked["valid"]:
                        costs.append(checked["totalCost"])
                answer = solve_branch_bound(task)
                self.assertTrue(answer["provenOptimal"])
                self.assertGreaterEqual(answer["improvements"], 1)
                self.assertEqual(answer["bestCost"], min(costs))

    def test_limit_never_claims_proof(self):
        task = generate_example(12, 3, 26)
        answer = solve_branch_bound(task, {"nodeLimit": 1})
        self.assertEqual(answer["status"], "limit_with_plan")
        self.assertFalse(answer["provenOptimal"])
        self.assertEqual(answer["nodesVisited"], 1)
        self.assertEqual(answer["initialSource"], "текущий ручной план")
        self.assertEqual(answer["bestCost"], evaluate(task)["totalCost"])
        self.assertEqual(answer["tree"][-1]["status"], "limit")
        self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])

    def test_limit_without_incumbent_does_not_claim_infeasibility(self):
        task = generate_example(3, 2, 3)
        task["assignment"] = {}
        answer = solve_branch_bound(task, {"nodeLimit": 1})
        self.assertEqual(answer["status"], "limit_no_plan")
        self.assertFalse(answer["provenInfeasible"])
        self.assertNotIn("bestAssignment", answer)

    def test_exhausted_search_proves_infeasibility(self):
        task = generate_example(2, 2, 3)
        task["sites"][0]["places"] = 1
        task["sites"][1]["travelTime"] = task["limitHours"] + 1
        task["assignment"] = {}
        answer = solve_branch_bound(task, {"nodeLimit": 100})
        self.assertEqual(answer["status"], "infeasible")
        self.assertTrue(answer["provenInfeasible"])
        self.assertNotIn("bestAssignment", answer)

    def test_invalid_node_limit_rejected(self):
        task = generate_example(2, 1, 3)
        for value in (0, 1.5, True, 1000001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                solve_branch_bound(task, {"nodeLimit": value})

    def test_removed_initial_plan_option_is_not_used(self):
        task = generate_example(3, 2, 3)
        previous_assignment = task["assignment"]
        task["assignment"] = {}
        answer = solve_branch_bound(task, {"nodeLimit": 1,
                                           "incumbentAssignment": previous_assignment})
        self.assertEqual(answer["initialSource"], "без начального плана")
        self.assertEqual(answer["status"], "limit_no_plan")
        self.assertNotIn("bestAssignment", answer)


if __name__ == "__main__":
    unittest.main()
