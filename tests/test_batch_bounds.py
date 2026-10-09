import importlib
import importlib.util
import unittest
from unittest.mock import patch
from dataclasses import replace
from test_prepare import problem
from dyadbridge.prepare import prepare
from dyadbridge.budget import Limits
from dyadbridge.errors import ResourceLimitError,InputError


class BoundsTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.sample'),'Batch preflight is not implemented')
        return importlib.import_module('dyadbridge.sample')

    def test_all_batch_refusals_precede_source(self):
        s=self.module();model,req=problem(['A','B'],[('A','B',1),('B','A',1)],'A','B')
        for kw in [{'max_events':1},{'max_draws':1},{'max_output_bytes':1},{'max_batch_bytes':1},{'max_reader_bytes':1},{'max_record_bytes':1}]:
            p=prepare(model,req,limits=Limits(**kw))
            with patch.object(s,'seeded_source',side_effect=AssertionError('RNG constructed')):
                with self.subTest(kw=kw),self.assertRaises(ResourceLimitError):s.sample_batch(p,samples=2,seed=17)

    def test_invalid_seed_and_count(self):
        s=self.module();p=prepare(*problem(['A'],[],'A','A'))
        for count,seed in [(0,0),(True,0),(10001,0),(1,True),(1,-1),(1,2**64)]:
            with self.subTest(count=count,seed=seed),self.assertRaises(InputError):s.sample_batch(p,samples=count,seed=seed)

    def test_forced_235_events_extreme_grid_and_no_postdraw_guards(self):
        from fractions import Fraction as F
        from io import BytesIO
        from dyadbridge.model import Model,BridgeRequest
        from dyadbridge.budget import WorkBudget
        from dyadbridge.serialize import read_jsonl
        from test_random import Tape
        s=self.module()
        a='A'+'x'*63;b='B'+'y'*63
        model=Model.from_dict({'schema':'dyadbridge.model.v1','states':[a,b],
            'rates':[{'from':a,'to':b,'rate':1},{'from':b,'to':a,'rate':1}]})
        t0=-(2**511-1)
        request=BridgeRequest.from_dict({'start':a,'end':b,'t0':t0,'t1':t0+64,
            'epsilon':'1/'+str(10**60),'time_bits':64},model)
        prepared=prepare(model,request);self.assertEqual(prepared.count_table.outcomes[-1],235)
        bounds=s.preflight_batch(prepared,1,17)
        for bin_ in (0,2**64-1):
            tape=Tape([prepared.count_table.total-1]+[bin_]*235)
            with patch.object(WorkBudget,'charge',side_effect=AssertionError('Policy guard after RNG')):
                histories=s._sample_histories(prepared,bounds,tape)
                self.assertEqual(len(histories[0].events),235)
                # Constructed bit-tape fixture, not claimed to be a seed17 replay.
                batch=s.Batch(model,request,prepared.limits,prepared.certificate,bounds.run_metadata,histories)
                jsonl=''.join(batch.to_jsonl()).encode();csv=''.join(batch.to_csv()).encode()
            self.assertLessEqual(max(len(jsonl),len(csv)),bounds.output_bytes)
            self.assertTrue(all(len(line)+1<=bounds.max_record_bytes for line in jsonl.splitlines()))
            self.assertEqual(read_jsonl(BytesIO(jsonl)).histories,histories)

    def test_reader_ingestion_work_is_preflighted_before_rng(self):
        from fractions import Fraction as F
        from dyadbridge.model import Model,Edge,BridgeRequest
        fib=[0,1]
        for _ in range(595):fib.append(fib[-1]+fib[-2])
        states=tuple('S%02d'%i for i in range(64))
        model=Model(states,tuple(Edge(i,63,F(fib[595],fib[596]) if i<24 else F(fib[594],fib[595])) for i in range(63)))
        request=BridgeRequest('S00','S00',F(0),F(0),F(1,2),1)
        prepared=prepare(model,request)
        s=self.module()
        with patch.object(s,'seeded_source',side_effect=AssertionError('RNG stage reached')):
            with self.assertRaises(ResourceLimitError) as caught:s.sample_batch(prepared,samples=1,seed=0)
        self.assertIn('reader',caught.exception.stage)

    def test_bounds_are_deterministic(self):
        s=self.module();p=prepare(*problem(['A','B'],[('A','B',1),('B','A',1)],'A','B'))
        a=s.preflight_batch(p,10,17);b=s.preflight_batch(p,10,17)
        self.assertEqual(a,b);self.assertGreater(a.output_bytes,0);self.assertGreater(a.batch_bytes,0)

if __name__=='__main__':unittest.main()
