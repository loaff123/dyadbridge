import importlib
import importlib.util
import io,json,csv
import unittest
from dyadbridge.prepare import prepare
from dyadbridge.sample import sample_batch,preflight_batch
from dyadbridge import schema
from test_prepare import problem


class SerializationTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.serialize'),'Serializer is not implemented')
        return importlib.import_module('dyadbridge.serialize')

    def batch(self,count=10):
        p=prepare(*problem(['A','B'],[('A','B',1),('B','A',1)],'A','B',time_bits=2))
        return p,sample_batch(p,samples=count,seed=17)

    def test_jsonl_round_trip_and_bounds(self):
        module=self.module();p,b=self.batch();text=''.join(b.to_jsonl())
        read=module.read_jsonl(io.BytesIO(text.encode()))
        self.assertEqual(read,b);self.assertEqual(''.join(read.to_jsonl()),text)
        records=[json.loads(line) for line in text.splitlines()]
        self.assertEqual(records[0]['record_type'],'run');self.assertEqual(records[-1]['record_type'],'complete')
        bound=preflight_batch(p,10,17)
        self.assertLessEqual(len(text.encode()),bound.output_bytes)
        self.assertTrue(all(len(line.encode())+1<=bound.max_record_bytes for line in text.splitlines()))

    def test_csv_self_contained_and_quoting(self):
        self.module();p,b=self.batch();text=''.join(b.to_csv())
        reader=csv.DictReader(io.StringIO(text));self.assertEqual(tuple(reader.fieldnames),schema.CSV_COLUMNS)
        logical=[]
        for row in reader:
            if row['record_type']=='event':
                data={k:(int(v) if k in ('sample_id','event_index','uniformization_ordinal','bin') else v) for k,v in row.items() if k!='metadata_json'}
            else:
                data=json.loads(row['metadata_json']);data['record_type']=row['record_type']
                if row['sample_id']:data['sample_id']=int(row['sample_id'])
            logical.append(data)
        self.assertEqual(logical,[json.loads(line) for line in b.to_jsonl()])
        self.assertLessEqual(len(text.encode()),preflight_batch(p,10,17).output_bytes)

    def test_frozen_hky_seed17_scientific_golden(self):
        from pathlib import Path
        from dyadbridge import load_model,BridgeRequest
        root=Path(__file__).parents[1]
        with (root/'examples/hky.json').open('rb') as stream:model=load_model(stream)
        request=BridgeRequest.from_dict({'start':'A','end':'G','t0':0,'t1':'1/5','time_bits':8},model)
        actual=[json.loads(line) for line in sample_batch(prepare(model,request),samples=3,seed=17).to_jsonl()]
        expected=[json.loads(line) for line in (root/'tests/fixtures/hky-seed17-v1.jsonl').read_text().splitlines()]
        expected[0]['runtime']=actual[0]['runtime']
        self.assertEqual(actual,expected)

    def test_zero_event_records_survive(self):
        module=self.module();p=prepare(*problem(['A'],[],'A','A'))
        b=sample_batch(p,samples=3,seed=0);raw=''.join(b.to_jsonl()).encode()
        self.assertEqual(len(module.read_jsonl(io.BytesIO(raw)).histories),3)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(''.join(b.to_csv()))))),5)

    def test_above_model_input_limit(self):
        module=self.module();p,b=self.batch(3000);raw=''.join(b.to_jsonl()).encode()
        self.assertGreater(len(raw),1048576)
        self.assertEqual(len(module.read_jsonl(io.BytesIO(raw)).histories),3000)

if __name__=='__main__':unittest.main()
