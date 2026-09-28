"""Проверка настоящего полного перебора и доказательств результата."""

import unittest
import os
from itertools import count
from unittest.mock import patch

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

    def test_search_checks_more_than_old_million_limit(self):
        task = generate_example(20, 2, 3)
        updates = []
        with patch("exhaustive.perf_counter", side_effect=count()):
            answer = solve_exhaustive(task, {"workers": 1}, progress=updates.append)
        self.assertEqual(answer["status"], "optimal")
        self.assertEqual(answer["checkedCount"], 2 ** 20)
        self.assertEqual(answer["checkedCount"], answer["validCount"] + answer["invalidCount"])
        self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])
        self.assertEqual(updates[0]["checkedCount"], 0)
        self.assertGreater(len(updates), 1)
        self.assertTrue(all(a["checkedCount"] < b["checkedCount"]
                            for a, b in zip(updates, updates[1:])))
        self.assertEqual(updates[-1]["totalCombinations"], answer["totalCombinations"])

    def test_parallel_matches_single_process(self):
        workers = min(4, os.cpu_count() or 1)
        if workers < 2:
            self.skipTest("Для проверки нужны два ядра процессора.")
        task = generate_example(18, 2, 7)
        single = solve_exhaustive(task, {"workers": 1})
        parallel = solve_exhaustive(task, {"workers": workers})
        self.assertEqual(parallel["workers"], workers)
        for key in ("status", "checkedCount", "validCount", "invalidCount",
                    "bestCost", "bestAssignment"):
            self.assertEqual(parallel[key], single[key])
        self.assertEqual(parallel["history"][-1]["checkedCount"], 2 ** 18)

    def test_complete_search_proves_infeasible(self):
        task = generate_example(2, 1, 3)
        task["sites"][0]["places"] = 0
        answer = solve_exhaustive(task)
        self.assertEqual(answer["status"], "infeasible")
        self.assertTrue(answer["provenInfeasible"])
        self.assertEqual(answer["checkedCount"], 1)
        self.assertEqual(answer["invalidCount"], 1)

if __name__ == "__main__":
    unittest.main()
