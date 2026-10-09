import importlib
import importlib.util
import itertools
import unittest
from fractions import Fraction as F
from test_prepare import problem


class EnumerationTests(unittest.TestCase):
    def test_independent_full_path_products(self):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.prepare'),'Preparer is not implemented')
        prepare=importlib.import_module('dyadbridge.prepare').prepare
        p=prepare(*problem(['A','B','C'],[('A','B',2),('A','C',1),('B','A',1),('B','C',1),('C','A',1)],'A','C','1/3'))
        D=3; R=[[F(0),F(2,3),F(1,3)],[F(1,3),F(1,3),F(1,3)],[F(1,3),F(0),F(2,3)]]
        for n in range(1,6):
            total=F(0)
            for mids in itertools.product(range(3),repeat=n-1):
                path=(0,)+mids+(2,); direct=F(1); conditional=F(1)
                for k,(i,j) in enumerate(zip(path,path[1:])):
                    direct*=R[i][j]
                    table=p.step_tables[n-k][i]
                    if table and j in table.outcomes:
                        at=table.outcomes.index(j); prior=table.cumulative[at-1] if at else 0
                        conditional*=F(table.cumulative[at]-prior,table.total)
                    else: conditional=F(0)
                total+=direct
                self.assertEqual(conditional,direct/F(p.backward[n][0],D**n))
            self.assertEqual(total,F(p.backward[n][0],D**n))

if __name__=='__main__':unittest.main()
