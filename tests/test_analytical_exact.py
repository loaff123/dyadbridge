import importlib.util
from pathlib import Path
import unittest
from fractions import Fraction as F
from math import factorial
from dyadbridge import Model,BridgeRequest,prepare


class AnalyticalExactTests(unittest.TestCase):
    def oracles(self):
        path=Path(__file__).parents[1]/'validation'/'analytical.py'
        self.assertTrue(path.exists(),'Independent analytical driver is not implemented')
        spec=importlib.util.spec_from_file_location('dyadbridge_oracles',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_hky_exact_beta(self):
        a=self.oracles();model,request=a.fixture('hky');p=prepare(model,request)
        start=model.states.index('A')
        for n,vector in enumerate(p.backward):
            self.assertEqual(F(vector[start],11**n),a.hky_beta(n))
        self.assertEqual(a.hky_beta(0),0);self.assertEqual(a.hky_beta(1),F(6,11))

    def test_birth_midpoint_count_mixture(self):
        a=self.oracles();model,request=a.fixture('birth',depth=3);p=prepare(model,request)
        value=a.birth_bin_cdf(p,3,F(1,2))
        self.assertGreater(value,0);self.assertLess(value,1)
        self.assertEqual(a.birth_bin_cdf(p,3,F(1)),1)
        self.assertEqual(a.birth_bin_cdf(p,3,F(0)),0)

if __name__=='__main__':unittest.main()
