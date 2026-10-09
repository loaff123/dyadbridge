"""Generate HKY histories and summarize their quantized event records."""
from collections import Counter
from fractions import Fraction
from pathlib import Path
from dyadbridge import load_model,BridgeRequest,prepare,sample_batch,read_jsonl

model_path=Path(__file__).with_name('hky.json')
with model_path.open('rb') as source:model=load_model(source)
request=BridgeRequest.from_dict({'start':'A','end':'G','t0':0,'t1':'1/5','time_bits':16},model)
batch=sample_batch(prepare(model,request),samples=100,seed=17)
output=Path('hky-histories.jsonl')
with output.open('x',encoding='utf-8',newline='') as stream:stream.writelines(batch.to_jsonl())
with output.open('rb') as stream:checked=read_jsonl(stream)
counts=Counter()
for history in checked.histories:
    for i,j,count in history.transitions:counts[(model.states[i],model.states[j])]+=count
print('Wrote',len(checked.histories),'complete histories to',output)
print('Total real transition counts:',dict(sorted(counts.items())))
print('Mean quantized occupation times:')
for i,state in enumerate(model.states):
    mean=sum((h.occupation[i] for h in checked.histories),Fraction(0))/len(checked.histories)
    print(state,str(mean),'(~',float(mean),')')
