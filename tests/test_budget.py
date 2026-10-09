import importlib
import importlib.util
import unittest
from fractions import Fraction


class BudgetTests(unittest.TestCase):
    def module(self, name):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.'+name), 'Required module is not implemented')
        return importlib.import_module('dyadbridge.'+name)

    def test_guarded_arithmetic(self):
        b = self.module('budget'); w = b.WorkBudget()
        self.assertEqual(w.lcm(6, 10), 30)
        self.assertEqual(w.add(-5, 3), -2)
        self.assertEqual(w.qadd(Fraction(1, 6), Fraction(1, 3)), Fraction(1, 2))
        self.assertEqual(w.qmul(Fraction(7, 9), Fraction(9, 14)), Fraction(1, 2))
        self.assertEqual(w.qdiv(Fraction(7, 9), Fraction(14, 9)), Fraction(1, 2))
        self.assertGreater(w.work_units, 0)

    def test_conservative_product_boundary(self):
        b=self.module('budget'); e=self.module('errors'); w=b.WorkBudget(b.Limits(max_integer_bits=8))
        with self.assertRaises(e.ResourceLimitError): w.mul(16, 16)
        self.assertEqual(w.mul(1, 255), 255)
        with self.assertRaises(e.ResourceLimitError): w.add(255, 1)

    def test_work_before_operation(self):
        b=self.module('budget'); e=self.module('errors'); w=b.WorkBudget(b.Limits(max_work=8))
        with self.assertRaises(e.ResourceLimitError): w.mul(7, 7)
        self.assertEqual(w.work_units, 0)

    def test_logical_reservation(self):
        b=self.module('budget'); e=self.module('errors'); ledger=b.LogicalLedger(300)
        ledger.acquire('one', 200)
        with self.assertRaises(e.ResourceLimitError): ledger.acquire('two', 101)
        with self.assertRaises(ValueError): ledger.acquire('one', 1)
        ledger.release('one'); ledger.acquire('two', 300)
        self.assertEqual(ledger.peak, 300)

    def test_limits_cannot_expand_or_coerce(self):
        b=self.module('budget'); e=self.module('errors')
        for kwargs in [{'max_states':65},{'max_cutoff':257},{'max_work':True},{'max_work':0},{'max_integer_bits':32769}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(e.InputError): b.Limits(**kwargs)
        self.assertEqual(b.Limits(max_cutoff=0).max_cutoff,0)

    def test_work_is_deterministic(self):
        b=self.module('budget'); first=b.WorkBudget(); second=b.WorkBudget()
        for w in (first,second): w.lcm(12,18); w.qadd(Fraction(1,11),Fraction(3,7))
        self.assertEqual(first.work_units, second.work_units)

if __name__ == '__main__': unittest.main()
