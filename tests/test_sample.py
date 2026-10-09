import importlib
import importlib.util
import itertools
import unittest
from collections import Counter
from fractions import Fraction as F
from math import factorial,prod
from test_prepare import problem
from test_random import Tape
from dyadbridge.prepare import prepare


class SampleTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.sample'),'Sampler is not implemented')
        return importlib.import_module('dyadbridge.sample')

    def test_projection_and_ticks(self):
        s=self.module()
        grid=s.QuantizationGrid.create(F(0),F(1),2)
        history=s.project_history(0,(0,1,1,0),(0,0,3),grid,2)
        self.assertEqual([(e.source,e.destination,e.bin,e.uniformization_ordinal) for e in history.events],[(0,1,0,1),(1,0,3,3)])
        self.assertEqual(history.occupation,(F(1,4),F(3,4)))
        self.assertEqual(history.transitions,((0,1,1),(1,0,1)))

    def test_all_sorted_bins_and_ties(self):
        s=self.module();patterns=Counter()
        grid=s.QuantizationGrid.create(F(-2),F(1),2)
        for raw in itertools.product(range(4),repeat=3):
            bins=tuple(sorted(raw));patterns[bins]+=1
            h=s.project_history(0,(0,1,0,1),bins,grid,2)
            self.assertEqual(len(h.events),3);self.assertEqual(sum(h.occupation),1)
            self.assertEqual([e.time for e in h.events],[F(-2)+F(k,4) for k in bins])
        self.assertEqual(len(patterns),20)
        for bins,count in patterns.items():self.assertEqual(count,factorial(3)//prod(factorial(n) for n in Counter(bins).values()))
        h=s.project_history(0,(0,1,0,1),(0,0,0),grid,2)
        self.assertEqual(h.occupation,(F(0),F(1)))

    def test_seeded_endpoint_and_replay(self):
        s=self.module();p=prepare(*problem(['A','B'],[('A','B',1),('B','A',1)],'A','B',time_bits=2))
        a=s.sample_batch(p,samples=50,seed=17);b=s.sample_batch(p,samples=50,seed=17)
        self.assertEqual(a,b)
        for h in a.histories:
            self.assertEqual(h.events[-1].destination,1)
            self.assertEqual(sum(h.occupation),1)
            self.assertEqual(sum(row[2] for row in h.transitions),len(h.events))
            self.assertLessEqual(h.uniformization_count,p.certificate.cutoff)

    def test_trivial_no_model_bits(self):
        s=self.module();p=prepare(*problem(['A'],[],'A','A','3',time_bits=2))
        bounds=s.preflight_batch(p,2,17)
        histories=s._sample_histories(p,bounds,Tape([]))
        self.assertTrue(all(not h.events for h in histories))
        self.assertEqual(histories[0].occupation,(F(3),))

if __name__=='__main__':unittest.main()
