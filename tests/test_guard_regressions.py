"""Regressions first reproduced by the focused independent resource audit."""
import io
import json
import unittest
from fractions import Fraction as F
from dyadbridge.budget import Limits,WorkBudget
from dyadbridge.model import Model,BridgeRequest,RunOptions,load_model
from dyadbridge.prepare import prepare
from dyadbridge.errors import InputError,ResourceLimitError
from test_prepare import problem


class ShortRead(io.BytesIO):
    def read(self,size=-1):return super().read(min(size,64))


class GuardRegressions(unittest.TestCase):
    def test_retained_input_bits_cannot_bypass_lowered_limit(self):
        model,req=problem(['A'],[],'A','A',epsilon='1/'+str(10**100),time_bits=1)
        with self.assertRaises(ResourceLimitError):prepare(model,req,limits=Limits(max_integer_bits=64))

    def test_comparison_intermediates_are_guarded(self):
        model,req=problem(['A','B'],[('A','B',1),('B','A',1)],'A','A','1/127',epsilon='1/2',time_bits=1)
        with self.assertRaises(ResourceLimitError):prepare(model,req,limits=Limits(max_integer_bits=9))

    def test_direct_values_preserve_canonical_input_envelope(self):
        value=F(2**510+1,2**511+1)
        from dyadbridge.model import Edge
        with self.assertRaises(InputError):Model(('A','B'),(Edge(0,1,value),))
        with self.assertRaises(InputError):BridgeRequest('A','A',value,value)

    def test_mapping_canonical_model_size_cap(self):
        states=['S%02d'%i+'x'*61 for i in range(64)]
        data={'schema':'dyadbridge.model.v1','states':states,
              'rates':[{'from':a,'to':b,'rate':2**511-1} for a in states for b in states if a!=b]}
        with self.assertRaises(InputError):Model.from_dict(data)

    def test_compound_temporaries_overlap(self):
        budget=WorkBudget(Limits(max_prepared_bytes=72))
        with self.assertRaises(ResourceLimitError):budget.qle(F(17,19),F(23,29))

    def test_decimal_accumulator_lifetime_is_reserved(self):
        from dyadbridge.rational import decimal_integer
        with self.assertRaises(ResourceLimitError):
            decimal_integer('123456789123456789',budget=WorkBudget(Limits(max_prepared_bytes=72),stage='ingestion'))

    def test_preflight_charges_large_decimal_export(self):
        from dyadbridge.sample import preflight_batch
        value=F(2**511-1)
        model=Model(('A',),())
        request=BridgeRequest('A','A',value,value,F(1,2),1)
        prepared=prepare(model,request,limits=Limits(max_work=5000))
        with self.assertRaises(ResourceLimitError):preflight_batch(prepared,1,0)

    def test_decoded_json_shape_refuses_before_materialization(self):
        from unittest.mock import patch
        import dyadbridge.model as module
        head=b'{"schema":"dyadbridge.model.v1","states":["A"],"rates":[],"extra":['
        chain=b'['*14+b'0'+b']'*14
        count=(1048576-len(head)-2+1)//(len(chain)+1)
        raw=head+b','.join([chain]*count)+b']}'
        self.assertLessEqual(len(raw)+1,1048576)
        for data in (raw,raw+b'x'):
            with patch.object(module.json,'loads',side_effect=AssertionError('Unbounded graph materialized')):
                with self.assertRaises(ResourceLimitError):module.load_model(io.BytesIO(data))

    def test_direct_run_options_validate(self):
        for args in [(0,0),(1,True),(1,-1),(1,2**64)]:
            with self.subTest(args=args),self.assertRaises(InputError):RunOptions(*args)

    def test_tiny_short_reads_use_one_bounded_buffer(self):
        import tracemalloc
        from dyadbridge.model import parse_json_bounded
        class OneByte(io.BytesIO):
            def read(self,size=-1):return memoryview(super().read(min(size,1))).tobytes()
        raw=b'{}'+b' '*(262144-2)
        tracemalloc.start()
        try:
            self.assertEqual(parse_json_bounded(OneByte(raw)),{})
            peak=tracemalloc.get_traced_memory()[1]
        finally:tracemalloc.stop()
        self.assertLess(peak,4*1024*1024)

    def test_short_read_does_not_hide_trailing_bytes(self):
        data=b'{"schema":"dyadbridge.model.v1","states":["A"],"rates":[]}'
        self.assertEqual(load_model(ShortRead(data)).states,('A',))
        with self.assertRaises(InputError):load_model(ShortRead(data+b' '*100+b'INVALID'))

    def test_refusal_context_is_json_and_stage_is_preparation(self):
        model,req=problem(['A','B'],[('A','B',1),('B','A',1)],'A','B','65')
        try:prepare(model,req)
        except ResourceLimitError as exc:json.dumps(exc.to_dict())
        else:self.fail('Expected mu refusal')
        model,req=problem(['A','B'],[('A','B',1),('B','A',1)],'A','B')
        try:prepare(model,req,limits=Limits(max_cutoff=0))
        except ResourceLimitError as exc:self.assertEqual(exc.stage,'preparation')
        else:self.fail('Expected cutoff refusal')

if __name__=='__main__':unittest.main()
