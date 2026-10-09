import importlib
import importlib.util
import unittest
from fractions import Fraction as F
from math import factorial
from dyadbridge.model import Model, BridgeRequest
from dyadbridge.budget import Limits
from dyadbridge.errors import ImpossibleEndpoint, ResourceLimitError


def problem(states, edges, start, end, horizon='1', **options):
    model=Model.from_dict({'schema':'dyadbridge.model.v1','states':states,
        'rates':[{'from':a,'to':b,'rate':r} for a,b,r in edges]})
    request=BridgeRequest.from_dict({'start':start,'end':end,'t0':0,'t1':horizon,**options},model)
    return model,request


class PrepareTests(unittest.TestCase):
    def prepare(self,*args,**kwargs):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.prepare'),'Preparer is not implemented')
        return importlib.import_module('dyadbridge.prepare').prepare(*args,**kwargs)

    def test_trivial_and_impossible(self):
        for horizon,edges in [('0',[('A','B',1)]),('2',[])]:
            p=self.prepare(*problem(['A','B'],edges,'A','A',horizon))
            self.assertEqual(p.certificate.cutoff,0); self.assertEqual(p.certificate.retained,1)
            self.assertEqual(p.certificate.tv_upper,0); self.assertEqual(p.count_table.outcomes,(0,))
            with self.assertRaises(ImpossibleEndpoint): self.prepare(*problem(['A','B'],edges,'A','B',horizon))
        with self.assertRaises(ImpossibleEndpoint):
            self.prepare(*problem(['A','B','C'],[('A','B',1)],'A','C'))

    def test_periodic_parity_and_count_formula(self):
        for end,parity in [('A',0),('B',1)]:
            p=self.prepare(*problem(['A','B'],[('A','B',1),('B','A',1)],'A',end,'3'))
            self.assertTrue(all(n%2==parity for n in p.count_table.outcomes))
            self.assertLessEqual(p.certificate.tv_upper,F(1,10**12))
            K=p.certificate.cutoff
            weights=[F(3**n,factorial(n)) if n%2==parity else F(0) for n in range(K+1)]
            self.assertEqual(p.certificate.retained,sum(weights))
            masses=[b-a for a,b in zip((0,)+p.count_table.cumulative,p.count_table.cumulative)]
            for n,mass in zip(p.count_table.outcomes,masses):
                self.assertEqual(F(mass,p.count_table.total),weights[n]/sum(weights))
            H=F(3**(K+1),factorial(K+1))/(1-F(3,K+2))
            self.assertEqual(p.certificate.tail_upper,H)
            self.assertEqual(p.certificate.tv_upper,H/(sum(weights)+H))

    def test_all_step_tables_are_prepared(self):
        p=self.prepare(*problem(['A','B','C'],[('A','B',2),('A','C',1),('B','A',1),('B','C',1)],'A','C','1/4'))
        for r in range(1,p.certificate.cutoff+1):
            for i in range(3):
                table=p.step_tables[r][i]
                if p.backward[r][i]:
                    self.assertIsNotNone(table)
                    self.assertEqual(table.total,p.backward[r][i])
                else:self.assertIsNone(table)
        with self.assertRaises(AttributeError): p.count_table=None

    def test_resource_refusals(self):
        model,req=problem(['A','B'],[('A','B',1),('B','A',1)],'A','B')
        for limits in [Limits(max_cutoff=0),Limits(max_work=1),Limits(max_prepared_bytes=1),Limits(max_entries=1),Limits(max_integer_bits=4)]:
            with self.subTest(limits=limits), self.assertRaises(ResourceLimitError):self.prepare(model,req,limits=limits)
        with self.assertRaises(ResourceLimitError):
            self.prepare(*problem(['A','B'],[('A','B',1),('B','A',1)],'A','B','65'))
        with self.assertRaises(ResourceLimitError):
            self.prepare(*problem(['A','B'],[('A','B','1/257'),('B','A',1)],'A','B'),limits=Limits(max_denominator_bits=8))

    def test_canonical_diagnostics(self):
        a=problem(['A','B'],[('A','B','1/2'),('B','A',1)],'A','B')
        b=problem(['B','A'],[('B','A','4/4'),('A','B','0.500')],'A','B')
        p,q=self.prepare(*a),self.prepare(*b)
        self.assertEqual(p.preparation_diagnostics,q.preparation_diagnostics)
        self.assertEqual(p.certificate,q.certificate)

if __name__=='__main__':unittest.main()
