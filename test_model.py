"""Проверки математической модели: python -m unittest -v."""

import unittest

from model import evaluate, generate_example


class ModelTests(unittest.TestCase):
    def test_generated_assignment_is_feasible_at_extreme_sizes(self):
        for n, m in ((1, 10), (12, 3), (80, 10)):
            with self.subTest(containers=n, sites=m):
                task = generate_example(n, m, 26)
                self.assertTrue(evaluate(task)["valid"])

    def test_every_container_must_be_assigned(self):
        task = generate_example(2, 1, 3)
        task["assignment"].pop(task["containers"][0]["id"])
        result = evaluate(task)
        self.assertFalse(result["valid"])
        self.assertTrue(any("Не назначен" in issue for issue in result["issues"]))

    def test_capacity_mass_power_and_time_are_hard_limits(self):
        task = generate_example(2, 1, 3)
        site = task["sites"][0]
        site["places"] = 1
        site["massLimit"] = 1
        site["powerLimit"] = 1
        task["limitHours"] = 1
        result = evaluate(task)
        self.assertFalse(result["valid"])
        self.assertGreaterEqual(len(result["issues"]), 4)

    def test_tariff_units_change_only_transport_part(self):
        task = generate_example(1, 1, 3)
        by_container = evaluate(task)["rows"][0]
        task["tariffMode"] = "ton_hour"
        by_ton = evaluate(task)["rows"][0]
        weight = task["containers"][0]["weight"]
        self.assertEqual(by_container["storageCost"], by_ton["storageCost"])
        self.assertEqual(by_ton["travelCost"], by_container["travelCost"] * weight)

    def test_all_generated_values_and_costs_are_integers(self):
        task = generate_example(20, 3, 26)
        for container in task["containers"]:
            for key in ("weight", "power", "storage"):
                self.assertIs(type(container[key]), int)
        for site in task["sites"]:
            for key in ("places", "massLimit", "powerLimit", "storageRate", "travelTime", "travelRate"):
                self.assertIs(type(site[key]), int)
        self.assertIs(type(task["limitHours"]), int)
        result = evaluate(task)
        self.assertIs(type(result["totalCost"]), int)
        for row in result["rows"]:
            for key in ("storageCost", "travelCost", "cost"):
                self.assertIs(type(row[key]), int)

    def test_fractional_input_is_rejected(self):
        for group, keys in (("containers", ("weight", "power", "storage")),
                            ("sites", ("places", "massLimit", "powerLimit",
                                       "storageRate", "travelTime", "travelRate"))):
            for key in keys:
                with self.subTest(group=group, key=key):
                    task = generate_example(2, 1, 3)
                    task[group][0][key] = 1.5
                    with self.assertRaisesRegex(ValueError, "целое"):
                        evaluate(task)
        task = generate_example(2, 1, 3)
        task["limitHours"] = 1.5
        with self.assertRaisesRegex(ValueError, "целое"):
            evaluate(task)
        with self.assertRaises(ValueError):
            generate_example(2.5, 1, 3)

if __name__ == "__main__":
    unittest.main()
