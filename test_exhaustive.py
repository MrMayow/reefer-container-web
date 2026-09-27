"""Проверка настоящего полного перебора и доказательств результата."""

import unittest

from branch_bound import solve_branch_bound
from exhaustive import solve_exhaustive
from model import evaluate, generate_example


class ExhaustiveTests(unittest.TestCase):
    def test_complete_search_matches_branch_bound_for_both_tariffs(self):
        for mode in ("container_hour", "ton_hour"):
            with self.subTest(mode=mode):
                task = generate_example(5, 3, 7)
                task["tariffMode"] = mode
                full = solve_exhaustive(task)
                branch = solve_branch_bound(task)
                self.assertEqual(full["status"], "optimal")
                self.assertTrue(full["provenOptimal"])
                self.assertEqual(full["totalCombinations"], "243")
                self.assertEqual(full["checkedCount"], 243)
                self.assertEqual(full["checkedCount"], full["validCount"] + full["invalidCount"])
                self.assertEqual(full["bestCost"], branch["bestCost"])
                self.assertTrue(evaluate({**task, "assignment": full["bestAssignment"]})["valid"])

    def test_history_contains_real_counts_and_valid_best_plans(self):
        task = generate_example(4, 2, 3)
        answer = solve_exhaustive(task)
        previous_checked = 0
        previous_best = None
        for stage in answer["history"]:
            self.assertGreaterEqual(stage["checkedCount"], previous_checked)
            self.assertEqual(stage["checkedCount"], stage["validCount"] + stage["invalidCount"])
            previous_checked = stage["checkedCount"]
            if stage["bestChromosome"] is not None:
                assignment = {container["id"]: task["sites"][stage["bestChromosome"][i]]["id"]
                              for i, container in enumerate(task["containers"])}
                checked = evaluate({**task, "assignment": assignment})
                self.assertTrue(checked["valid"])
                self.assertEqual(stage["bestCost"], checked["totalCost"])
                if previous_best is not None:
                    self.assertLessEqual(stage["bestCost"], previous_best)
                previous_best = stage["bestCost"]
        self.assertEqual(answer["history"][-1]["checkedCount"], answer["checkedCount"])

    def test_limit_does_not_claim_proof(self):
        task = generate_example(4, 2, 3)
        answer = solve_exhaustive(task, {"combinationLimit": 1})
        self.assertEqual(answer["status"], "limit_no_plan")
        self.assertFalse(answer["provenOptimal"])
        self.assertFalse(answer["provenInfeasible"])
        self.assertEqual(answer["checkedCount"], 1)
        self.assertNotIn("bestAssignment", answer)

    def test_limit_with_plan_is_not_proof(self):
        task = generate_example(4, 2, 3)
        answer = solve_exhaustive(task, {"combinationLimit": 15})
        self.assertEqual(answer["status"], "limit_with_plan")
        self.assertFalse(answer["provenOptimal"])
        self.assertEqual(answer["checkedCount"], 15)
        self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])

    def test_complete_search_proves_infeasible(self):
        task = generate_example(2, 1, 3)
        task["sites"][0]["places"] = 0
        answer = solve_exhaustive(task)
        self.assertEqual(answer["status"], "infeasible")
        self.assertTrue(answer["provenInfeasible"])
        self.assertEqual(answer["checkedCount"], 1)
        self.assertEqual(answer["invalidCount"], 1)

    def test_invalid_limit_rejected(self):
        task = generate_example(2, 2, 3)
        for value in (0, 1.5, True, 5000001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                solve_exhaustive(task, {"combinationLimit": value})


if __name__ == "__main__":
    unittest.main()
