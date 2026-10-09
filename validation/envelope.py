"""Reproducible supported/refused envelope, each case in a fresh subprocess."""
import argparse,json,platform,resource,subprocess,sys,time
from pathlib import Path
from fractions import Fraction as F
from analytical import fixture
from dyadbridge import prepare,sample_batch
from dyadbridge.errors import DyadbridgeError


def one(case):
    start=time.perf_counter()
    try:
        model,request=fixture(case['name'],**{k:(F(v) if k=='mu' else v) for k,v in case.items() if k!='name'})
        p=prepare(model,request);prepared=time.perf_counter();b=sample_batch(p,samples=10,seed=17);sampled=time.perf_counter()
        return {**case,'status':'prepared-and-sampled','preparation_seconds':prepared-start,'sample_seconds':sampled-prepared,
                'histories_per_second':10/(sampled-prepared),'cutoff':p.certificate.cutoff,
                **p.preparation_diagnostics.to_dict(),'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    except DyadbridgeError as exc:
        return {**case,'status':'refused','seconds':time.perf_counter()-start,'error':exc.to_dict(),
                'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def run(output):
    cases=[dict(name='dense',n=n,mu=str(mu),sparse=sparse) for n in (4,8,32,64) for mu in (1,4,16,64) for sparse in (False,True)]
    cases += [dict(name='rare'),dict(name='hky'),dict(name='birth',depth=20),dict(name='birth',depth=60),dict(name='rare_branch'),dict(name='coprime'),dict(name='cycle'),dict(name='periodic',mu='64')]
    results=[]
    for case in cases:
        child=subprocess.run([sys.executable,__file__,'--case',json.dumps(case)],capture_output=True,text=True,check=True)
        row=json.loads(child.stdout);results.append(row);print(case,row['status'],flush=True)
    Path(output).write_text(json.dumps({'python':platform.python_version(),'platform':platform.platform(),'processor':platform.processor(),
        'rss_unit':'KiB on the reference Linux machine, per fresh case process','cases':results},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--case');a=p.parse_args()
    if a.case:print(json.dumps(one(json.loads(a.case))))
    elif a.output:run(a.output)
    else:p.error('--output or --case required')
