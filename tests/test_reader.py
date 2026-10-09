import importlib,importlib.util,io,json,sys
import unittest
from fractions import Fraction as F
from test_prepare import problem
from dyadbridge.prepare import prepare
from dyadbridge.sample import sample_batch
from dyadbridge.errors import InputError,ResourceLimitError
from dyadbridge.rational import format_rational
from dyadbridge.schema import canonical


class ReaderTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.serialize'),'Reader is not implemented')
        return importlib.import_module('dyadbridge.serialize')

    def records(self):
        p=prepare(*problem(['A','B'],[('A','B',1),('B','A',1)],'A','B',time_bits=2))
        b=sample_batch(p,samples=1,seed=17)
        return [json.loads(line) for line in b.to_jsonl()]

    def test_malformed_records(self):
        module=self.module();original=self.records()
        def raw(records):return ''.join(canonical(x)+'\n' for x in records).encode()
        mutations=[]
        for field,value in [('model_hash','0'*64),('run_hash','0'*64),('schema','future'),('sample_count',True)]:
            rows=json.loads(json.dumps(original));rows[0][field]=value;mutations.append(raw(rows))
        for field,value in [('bin',4),('uniformization_ordinal',0),('time','999'),('from','B'),('event_index',99)]:
            rows=json.loads(json.dumps(original));next(x for x in rows if x['record_type']=='event')[field]=value;mutations.append(raw(rows))
        mutations.extend([raw(original)[:-1],raw(original[:-1]),raw(original)+b'{}\n',b'\xff\n',b'['*17+b'0'+b']'*17+b'\n',b' '*8388609+b'\n',raw(original).replace(b'"record_type":"run"',b'"record_type":"run","record_type":"run"',1),raw(original).replace(b'"sample_count":1',b'"sample_count":NaN',1)])
        for value in mutations:
            with self.subTest(prefix=value[:80]),self.assertRaises((InputError,ResourceLimitError)):
                module.read_jsonl(io.BytesIO(value))

    def test_footer_boolean_counts_and_declared_mu_are_rejected(self):
        module=self.module()
        for edit in ('footer','mu','method'):
            rows=self.records()
            if edit=='footer':rows[-1]['sample_count']=True
            elif edit=='mu':rows[0]['certificate']['mu']='65'
            else:
                rows[0]['certificate'].update(method='deterministic-zero-horizon',cutoff=0,
                    retained_mass='1',tail_upper='0',tv_upper='0',batch_tv_upper='0')
            raw=''.join(canonical(row)+'\n' for row in rows).encode()
            with self.subTest(edit=edit),self.assertRaises(InputError):module.read_jsonl(io.BytesIO(raw))

    def test_large_rational_tokens_without_global_setting_change(self):
        module=self.module();rows=self.records();before=sys.get_int_max_str_digits()
        d=10**5000+1
        rows[0]['certificate']['retained_mass']='1'
        rows[0]['certificate']['tail_upper']=format_rational(F(1,d))
        rows[0]['certificate']['tv_upper']=format_rational(F(1,d+1))
        rows[0]['certificate']['batch_tv_upper']=format_rational(F(1,d+1))
        raw=''.join(canonical(row)+'\n' for row in rows).encode()
        self.assertEqual(module.read_jsonl(io.BytesIO(raw)).certificate.tail_upper,F(1,d))
        self.assertEqual(sys.get_int_max_str_digits(),before)

    def test_hashes_are_not_event_authentication(self):
        module=self.module();rows=self.records()
        # A different internally consistent history does not change input/run IDs.
        sample=rows[1];sample['uniformization_count']=1;sample['real_event_count']=1
        sample['occupation']=[{'state':'A','duration':'0'},{'state':'B','duration':'1'}]
        sample['transitions']=[{'from':'A','to':'B','count':1}]
        event={'record_type':'event','sample_id':0,'event_index':0,'uniformization_ordinal':1,'from':'A','to':'B','bin':0,'time':'0'}
        footer=rows[-1];footer['event_count']=1
        raw=''.join(canonical(x)+'\n' for x in [rows[0],sample,event,footer]).encode()
        read=module.read_jsonl(io.BytesIO(raw))
        self.assertEqual(read.histories[0].events[0].bin,0)

if __name__=='__main__':unittest.main()
