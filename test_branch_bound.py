"""Проверка минимальной стоимости, ограниченного поиска и этапов."""

from itertools import product
import unittest

from branch_bound import solve_branch_bound
from genetic import solve_genetic
from model import evaluate, generate_example


class BranchBoundTests(unittest.TestCase):
    def test_matches_exhaustive_search_for_both_tariffs(self):
        for mode in ("container_hour", "ton_hour"):
            with self.subTest(mode=mode):
                task = generate_example(5, 3, 7)
                task["tariffMode"] = mode
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

    def test_limit_never_claims_proof(self):
        task = generate_example(12, 3, 26)
        answer = solve_branch_bound(task, {"nodeLimit": 1})
        self.assertEqual(answer["status"], "limit_with_plan")
        self.assertFalse(answer["provenOptimal"])
        self.assertEqual(answer["nodesVisited"], 1)
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

    def test_genetic_plan_can_start_limited_exact_search(self):
        task = generate_example(20, 3, 26)
        genetic = solve_genetic(task)
        answer = solve_branch_bound(task, {"nodeLimit": 1,
                                           "incumbentAssignment": genetic["bestAssignment"]})
        self.assertEqual(answer["status"], "limit_with_plan")
        self.assertFalse(answer["provenOptimal"])
        self.assertLessEqual(answer["bestCost"], genetic["bestCost"])
        self.assertEqual(answer["initialSource"], "переданный допустимый план")

    def test_invalid_initial_plan_is_rejected(self):
        task = generate_example(3, 2, 3)
        with self.assertRaisesRegex(ValueError, "начальный план"):
            solve_branch_bound(task, {"incumbentAssignment": {}})


if __name__ == "__main__":
    unittest.main()
