"""Проверки генетического поиска и его истории."""

import unittest

from genetic import solve_genetic
from model import evaluate, generate_example


class GeneticTests(unittest.TestCase):
    def test_result_and_each_shown_stage_are_feasible(self):
        task = generate_example(12, 3, 26)
        original_cost = evaluate(task)["totalCost"]
        answer = solve_genetic(task, {"generations": 20, "populationSize": 24, "seed": 7})
        self.assertEqual(answer["status"], "found")
        self.assertFalse(answer["provenOptimal"])
        self.assertEqual(len(answer["history"]), 21)
        self.assertLessEqual(answer["bestCost"], original_cost)
        costs = []
        for record in answer["history"]:
            assignment = {container["id"]: task["sites"][record["bestChromosome"][i]]["id"]
                          for i, container in enumerate(task["containers"])}
            checked = evaluate({**task, "assignment": assignment})
            self.assertTrue(checked["valid"])
            self.assertEqual(checked["totalCost"], record["bestCost"])
            costs.append(record["bestCost"])
        self.assertEqual(costs, sorted(costs, reverse=True))
        self.assertEqual(costs[-1], answer["bestCost"])
        self.assertTrue(evaluate({**task, "assignment": answer["bestAssignment"]})["valid"])

    def test_same_seed_repeats_search(self):
        task = generate_example(10, 3, 9)
        options = {"generations": 8, "populationSize": 12, "seed": 42}
        self.assertEqual(solve_genetic(task, options), solve_genetic(task, options))

    def test_no_plan_found_is_not_a_proof(self):
        task = generate_example(2, 1, 3)
        task["sites"][0]["places"] = 0
        answer = solve_genetic(task, {"generations": 3, "populationSize": 4})
        self.assertEqual(answer["status"], "not_found")
        self.assertFalse(answer["provenOptimal"])
        self.assertNotIn("bestAssignment", answer)

    def test_fractional_or_excessive_settings_are_rejected(self):
        task = generate_example(2, 1, 3)
        for options in ({"generations": 1.5}, {"populationSize": 1000}, {"seed": -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                solve_genetic(task, options)


if __name__ == "__main__":
    unittest.main()
