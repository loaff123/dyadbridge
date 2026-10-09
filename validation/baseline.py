"""Unmodified pinned mbridges full-path comparison on ordinary models.

Supply its separately obtained, license-preserved source. No network downloads.
"""
import argparse,collections,importlib.metadata,json,logging,math,platform,sys,time,warnings
from pathlib import Path
from fractions import Fraction as F
from analytical import fixture
from dyadbridge import prepare,sample_batch


def summarize(paths,start,end,M):
    histogram=collections.Counter();midpoint=collections.Counter();first_before=0
    for events in paths:
        histogram[len(events)]+=1;state=start
        for bin_,new in events:
            if bin_<M//2:state=new
        midpoint[state]+=1
        hits=[bin_ for bin_,new in events if new==end]
        first_before+=bool(hits and min(hits)<M//2)
    size=len(paths)
    return {'complete_paths':size,'jump_count_histogram':dict(sorted(histogram.items())),
            'midpoint_state_histogram':dict(sorted(midpoint.items())),
            'first_hit_before_midpoint':first_before,'first_hit_fraction':first_before/size if size else None,
            'first_hit_monte_carlo_se':math.sqrt((first_before/size)*(1-first_before/size)/size) if size else None}


def run(args):
    sys.path.insert(0,str(Path(args.mbridges_source).resolve()))
    if args.deps:sys.path.insert(0,str(Path(args.deps).resolve()))
    import numpy as np
    import scipy
    from mbridges.markov import KMonteCarloBridge
    logging.getLogger().setLevel(logging.ERROR)
    reports=[];M=1<<8
    for name,kwargs in [('periodic',{'mu':F(1)}),('hky',{})]:
        model,request=fixture(name,**kwargs)
        from dyadbridge import BridgeRequest
        request=BridgeRequest.from_dict({**request.to_dict(),'time_bits':8},model)
        p=prepare(model,request);start=model.states.index(request.start);end=model.states.index(request.end)
        rates=np.zeros((len(model.states),len(model.states)))
        for edge in model.edges:rates[edge.destination,edge.source]=float(edge.rate)
        T=float(request.t1-request.t0);baseline=[];failures=[];captured=[];begun=time.perf_counter()
        for seed in range(args.baseline_samples):
            try:
                with warnings.catch_warnings(record=True) as warning_rows:
                    warnings.simplefilter('always')
                    engine=KMonteCarloBridge(rates,start,end,T,seed=seed)
                    while not engine.step():pass
                    trajectory=engine.get_trajectory()
                if int(trajectory[-1,1])!=end:raise RuntimeError('Baseline did not reach endpoint')
                events=[]
                for t,state in trajectory[1:,:2]:
                    bin_=math.floor(float(t)/T*M)
                    if not 0<=bin_<M:raise RuntimeError('Baseline event outside interval')
                    events.append((bin_,int(state)))
                baseline.append(events)
                if warning_rows:captured.append({'seed':seed,'warnings':sorted(set(str(w.message) for w in warning_rows))})
            except Exception as exc:failures.append({'seed':seed,'type':type(exc).__name__,'message':str(exc)})
            if (seed+1)%128==0:print(name,'baseline attempts',seed+1,flush=True)
        baseline_seconds=time.perf_counter()-begun;begun=time.perf_counter()
        batch=sample_batch(p,samples=args.dyad_samples,seed=20261009)
        dyad_seconds=time.perf_counter()-begun
        paths=[[(event.bin,event.destination) for event in h.events] for h in batch.histories]
        reports.append({'model':name,'states':list(model.states),'baseline_attempts':args.baseline_samples,'failures':failures,
                        'warnings':captured,'baseline_seconds':baseline_seconds,'dyad_prepared_sampling_seconds':dyad_seconds,
                        'baseline':summarize(baseline,start,end,M),'dyadbridge':summarize(paths,start,end,M),
                        'distribution_comparison_valid':not failures})
    payload={'mbridges_commit':'b567f07c4f703e07e14f27cabee9609f2db723e1','python':platform.python_version(),
             'numpy':np.__version__,'scipy':scipy.__version__,'opt_einsum':importlib.metadata.version('opt-einsum'),
             'time_bits':8,'baseline_settings':'unmodified CPU KMonteCarloBridge, default macheps, seeds 0..N-1',
             'qualification':'All attempts and failures retained; no retry/filtering. Baseline float binning has a near-boundary caveat. Monte Carlo agreement is not proof.',
             'cases':reports}
    Path(args.output).write_text(json.dumps(payload,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mbridges-source',required=True);p.add_argument('--deps');p.add_argument('--output',required=True)
    p.add_argument('--baseline-samples',type=int,default=1024);p.add_argument('--dyad-samples',type=int,default=4096);run(p.parse_args())
