"""Independent development oracles; mpmath is not a runtime dependency.

High-precision comparisons corroborate results, not the rational certificate.
"""
import argparse
from fractions import Fraction as F
from math import comb
from pathlib import Path
import json
import sys
from dyadbridge import Model,BridgeRequest,prepare
from dyadbridge.rational import format_rational


def fixture(name,*,depth=60,n=64,mu=F(4),sparse=False):
    if name=='hky':
        names=['A','G','C','T'];q=[[-55,30,15,10],[20,-45,15,10],[10,15,-45,20],[10,15,30,-55]]
        edges=[(a,b,F(q[i][j],49)) for i,a in enumerate(names) for j,b in enumerate(names) if i!=j]
        start,end,T='A','G',F(1,5)
    elif name=='rare':names=['S0','S1'];edges=[('S0','S1',F(1,10**18)),('S1','S0',F(1))];start,end,T='S0','S1',F(1)
    elif name=='periodic':names=['S0','S1'];edges=[('S0','S1',F(1)),('S1','S0',F(1))];start,end,T='S0','S1',F(mu)
    elif name=='birth':
        names=['S%02d'%i for i in range(depth+1)];edges=[(names[i],names[i+1],F(1)) for i in range(depth)]
        start,end,T=names[0],names[-1],F(1,5)
    elif name=='rare_branch':
        names=['A','B','C'];r=F(1,10**100);edges=[('A','B',r),('A','C',1-r)];start,end,T='A','B',F(1,5)
    elif name=='coprime':
        names=['A','B','C'];edges=[('A','B',F(1,2**257-1)),('A','C',F(1,2**263-1)),('B','A',F(1))];start,end,T='A','B',F(1)
    elif name=='cycle':
        names=['A','B','C'];edges=[('A','B',F(2)),('B','C',F(3)),('C','A',F(1))];start,end,T='A','C',F(1,3)
    else:
        names=['S%02d'%i for i in range(n)]
        edges=[(names[i],names[j],F(1+(17*i+31*j+7)%7,64)) for i in range(n) for j in range(n)
               if i!=j and (not sparse or j==(i+1)%n or (13*i+17*j)%5==0)]
        rate=max(sum((r for a,b,r in edges if a==state),F(0)) for state in names)
        start,end,T=names[0],names[-1],F(mu)/rate
    model=Model.from_dict({'schema':'dyadbridge.model.v1','states':names,
        'rates':[{'from':a,'to':b,'rate':format_rational(r)} for a,b,r in edges]})
    request=BridgeRequest.from_dict({'start':start,'end':end,'t0':0,'t1':format_rational(T),'time_bits':16},model)
    return model,request


def hky_beta(n):return F(3,10)+F(3,10)*F(1,11)**n-F(3,5)*F(-4,11)**n


def birth_bin_cdf(prepared,depth,u):
    value=F(0);previous=0
    for n,cumulative in zip(prepared.count_table.outcomes,prepared.count_table.cumulative):
        mass=F(cumulative-previous,prepared.count_table.total);previous=cumulative
        probability=sum((F(comb(n,j))*u**j*(1-u)**(n-j) for j in range(depth,n+1)),F(0))
        value+=mass*probability
    return value


def run(output):
    import mpmath as mp
    mp.mp.dps=180
    def scalar(value):return mp.mpf(value.numerator)/value.denominator
    results=[]
    for name,kwargs in [('hky',{}),('rare',{}),('birth',{'depth':20}),('birth',{'depth':60}),('periodic',{'mu':F(3)}),('cycle',{}),('dense',{'n':8}),('dense',{'n':64})]:
        model,request=fixture(name,**kwargs);p=prepare(model,request);T=scalar(request.t1-request.t0)
        def oracle():
            if name=='hky':return mp.mpf(3)/10+mp.mpf(3)/10*mp.exp(-50*T/49)-mp.mpf(3)/5*mp.exp(-75*T/49)
            if name=='rare':
                a=mp.mpf(1)/10**18;return a/(1+a)*(-mp.expm1(-(1+a)*T))
            if name=='birth':return mp.gammainc(kwargs['depth'],0,T)/mp.factorial(kwargs['depth']-1)
            if name=='periodic':return -mp.expm1(-2*T)/2
            n=len(model.states);Q=mp.matrix(n)
            for edge in model.edges:Q[edge.source,edge.destination]=scalar(edge.rate)
            for i in range(n):Q[i,i]=-sum(Q[i,j] for j in range(n) if i!=j)
            return mp.expm(Q*T)[model.states.index(request.start),model.states.index(request.end)]
        first=oracle();dps=max(180,int(mp.ceil(-mp.log10(first)))+12+50)
        mp.mp.dps=dps;expected=oracle()
        with mp.workdps(dps+40):refined=oracle()
        stability=abs(expected-refined)
        assert stability < max(mp.mpf('1e-150'),abs(refined)*mp.mpf('1e-140'))
        lower=mp.exp(-scalar(p.certificate.mu))*scalar(p.certificate.retained)
        upper=mp.exp(-scalar(p.certificate.mu))*scalar(p.certificate.retained+p.certificate.tail_upper)
        assert lower <= refined <= upper,(name,lower,refined,upper)
        item={'name':name,**{k:format_rational(v) if isinstance(v,F) else v for k,v in kwargs.items()},'dps':dps,
              'endpoint':mp.nstr(refined,60),'cutoff':p.certificate.cutoff,'tv_upper':format_rational(p.certificate.tv_upper),
              'oracle_precision_stability_error':mp.nstr(stability,8)}
        if name=='birth':
            cdf=birth_bin_cdf(p,kwargs['depth'],F(1,2))
            expected_cdf=mp.gammainc(kwargs['depth'],0,T/2)/mp.gammainc(kwargs['depth'],0,T)
            error=abs(scalar(cdf)-expected_cdf)
            assert error <= scalar(p.certificate.tv_upper)
            item['conditional_midpoint_hitting_error']=mp.nstr(error,20)
        if name=='hky':
            a=model.states.index('A')
            assert all(F(row[a],11**n)==hky_beta(n) for n,row in enumerate(p.backward))
            item['exact_beta_checks']=len(p.backward)
        results.append(item);print(name,kwargs,'passed',flush=True)
    payload={'status':'passed','python':sys.version.split()[0],'mpmath':mp.__version__,'cases':results,
             'qualification':'High-precision transcendental evaluations are numerical cross-checks, not directed-rounding proofs.'}
    Path(output).write_text(json.dumps(payload,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
