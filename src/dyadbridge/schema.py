"""Frozen output schema and canonical identity encoding. No network or sampling."""
import csv
import hashlib
import io
import json
import platform
from .rational import format_rational, decimal_string

VERSION='0.1.0'
SCHEMA='dyadbridge.batch.v1'
ALGORITHM='integer-uniformization-v1'
RNG='cpython-mt19937-getrandbits-v1'
TARGET='floor-dyadic-real-events-v1'
CSV_COLUMNS=('record_type','sample_id','event_index','uniformization_ordinal','from','to','bin','time','metadata_json')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


def identity(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def json_line(record):
    return canonical(record)+'\n'


def csv_line(record):
    row={key:'' for key in CSV_COLUMNS}
    row['record_type']=record['record_type']
    if record['record_type']=='event':
        for key in CSV_COLUMNS[:-1]:row[key]=record[key]
    else:
        if 'sample_id' in record:row['sample_id']=record['sample_id']
        row['metadata_json']=canonical({k:v for k,v in record.items() if k not in ('record_type','sample_id')})
    out=io.StringIO(newline='')
    writer=csv.DictWriter(out,fieldnames=CSV_COLUMNS,lineterminator='\n')
    writer.writerow(row)
    return out.getvalue()


def csv_header():
    out=io.StringIO(newline='');csv.writer(out,lineterminator='\n').writerow(CSV_COLUMNS)
    return out.getvalue()


def run_record(prepared,samples,seed,batch_tv,*,budget=None):
    model=prepared.model.to_dict(budget=budget);request=prepared.request.to_dict(budget=budget);limits=prepared.limits.to_dict()
    mh=identity(model);rh=identity({'model_hash':mh,'request':request,'limits':limits})
    seed_text=decimal_string(seed,budget=budget)
    run_hash=identity({'request_hash':rh,'seed':seed_text,'sample_count':samples,'package_version':VERSION,
                       'algorithm':ALGORITHM,'rng':RNG,'schema':SCHEMA})
    c=prepared.certificate
    cert=dict(method=c.method,target_law=TARGET,**{'lambda':format_rational(c.lambda_,budget=budget)},
              mu=format_rational(c.mu,budget=budget),cutoff=c.cutoff,retained_mass=format_rational(c.retained,budget=budget),
              tail_upper=format_rational(c.tail_upper,budget=budget),tv_upper=format_rational(c.tv_upper,budget=budget),
              epsilon=format_rational(c.epsilon,budget=budget),time_bits=c.time_bits,
              strict_time_displacement_upper=format_rational(c.time_displacement,budget=budget),
              batch_tv_upper=format_rational(batch_tv,budget=budget),randomness_assumption='independent-unbiased-bits',
              model_assumption='supplied-rational-generator')
    return dict(record_type='run',schema=SCHEMA,package_version=VERSION,algorithm=ALGORITHM,rng=RNG,
                runtime={'implementation':platform.python_implementation(),'version':platform.python_version()},
                model=model,request=request,limits=limits,model_hash=mh,request_hash=rh,run_hash=run_hash,
                seed=seed_text,sample_count=samples,certificate=cert,preparation=prepared.preparation_diagnostics.to_dict())


def sample_record(model,request,history):
    return dict(record_type='sample',sample_id=history.sample_id,start=request.start,end=request.end,
                t0=format_rational(request.t0),t1=format_rational(request.t1),
                uniformization_count=history.uniformization_count,real_event_count=len(history.events),
                occupation=[{'state':state,'duration':format_rational(duration)} for state,duration in zip(model.states,history.occupation)],
                transitions=[{'from':model.states[i],'to':model.states[j],'count':count} for i,j,count in history.transitions])


def event_record(model,sample_id,event):
    return dict(record_type='event',sample_id=sample_id,event_index=event.event_index,
                uniformization_ordinal=event.uniformization_ordinal,**{'from':model.states[event.source]},
                to=model.states[event.destination],bin=event.bin,time=format_rational(event.time))


def complete_record(samples,events,run_hash):
    return dict(record_type='complete',sample_count=samples,event_count=events,run_hash=run_hash)
