"""Preflighted sampling and exact quantized-event projection."""
from dataclasses import dataclass
from fractions import Fraction as F
from math import lcm
from .budget import WorkBudget,int_bytes,tuple_bytes,rational_bytes
from .errors import InputError,ResourceLimitError,InvariantError
from .model import strict_integer,Model,BridgeRequest,decode_json
from .prepare import PreparedBridge
from .random import seeded_source,choose,getbits
from . import schema


@dataclass(frozen=True)
class QuantizationGrid:
    t0:F
    horizon:F
    bits:int
    denominator:int
    origin:int
    step:int
    tick_denominator:int

    @classmethod
    def create(cls,t0,horizon,bits,*,budget=None):
        w=budget or WorkBudget(stage='batch-preflight')
        M=1<<bits
        tick_den=w.mul(horizon.denominator,M)
        denominator=w.lcm(t0.denominator,tick_den)
        origin=w.mul(t0.numerator,w.div(denominator,t0.denominator))
        step=w.mul(horizon.numerator,w.div(denominator,tick_den))
        return cls(t0,horizon,bits,denominator,origin,step,tick_den)

    def time(self,bin_):
        return F(self.origin+self.step*bin_,self.denominator)


@dataclass(frozen=True)
class Event:
    event_index:int
    uniformization_ordinal:int
    source:int
    destination:int
    bin:int
    time:F


@dataclass(frozen=True)
class History:
    sample_id:int
    uniformization_count:int
    events:tuple
    occupation:tuple
    transitions:tuple


@dataclass(frozen=True)
class RunMetadata:
    seed:int
    sample_count:int
    run_hash:str
    header_json:str


@dataclass(frozen=True)
class BatchBounds:
    samples:int
    seed:int
    grid:QuantizationGrid
    batch_bytes:int
    output_bytes:int
    reader_bytes:int
    max_record_bytes:int
    run_metadata:RunMetadata


@dataclass(frozen=True)
class Batch:
    model:object
    request:object
    limits:object
    certificate:object
    run_metadata:RunMetadata
    histories:tuple

    def to_jsonl(self):
        from .serialize import to_jsonl
        return to_jsonl(self)

    def to_csv(self):
        from .serialize import to_csv
        return to_csv(self)


def _limit(value,ceiling,name):
    if value>ceiling:raise ResourceLimitError('Whole-batch preflight ceiling exceeded',stage='batch-preflight',
                                             limit=name,ceiling=ceiling,predicted=value)


def _digits(bits):return max(1,(bits*30103+99999)//100000)


def _rational_prototype(numerator_bits,denominator_bits,negative=False):
    return ('-' if negative else '')+'9'*_digits(numerator_bits)+'/'+'9'*_digits(denominator_bits)


def preflight_batch(prepared,samples,seed):
    if type(prepared) is not PreparedBridge:raise InputError('Expected PreparedBridge')
    return _preflight_metadata(prepared,samples,seed)


def _preflight_metadata(prepared,samples,seed,*,original_header=None):
    """Shared sizing for trusted preparation metadata or bounded decoded metadata."""
    strict_integer(samples,1,10000,'samples');strict_integer(seed,0,2**64-1,'seed')
    limits=prepared.limits;K=prepared.certificate.cutoff;n=len(prepared.model.states)
    _limit(samples,limits.max_samples,'samples');_limit(samples*K,limits.max_events,'event_slots')
    _limit(samples*(2*K+1),limits.max_draws,'logical_draw_requests')
    w=WorkBudget(limits,stage='batch-preflight')
    # Covers bounded temporary model/header/prototype Python containers and text.
    w.ledger.acquire('metadata-and-prototypes',16777216)
    horizon=w.qadd(prepared.request.t1,w.fraction(-prepared.request.t0.numerator,prepared.request.t0.denominator))
    grid=QuantizationGrid.create(prepared.request.t0,horizon,prepared.request.time_bits,budget=w)
    M=1<<grid.bits
    last=w.add(grid.origin,w.mul(grid.step,M-1))
    time_bits=max(1,abs(grid.origin).bit_length(),abs(last).bit_length())+1
    w.check_bits(time_bits);den_bits=grid.denominator.bit_length()
    occ_bits=max(1,w.mul(abs(horizon.numerator),M).bit_length())
    occ_den_bits=grid.tick_denominator.bit_length()
    tv=w.qmul(F(samples),prepared.certificate.tv_upper)
    if tv>1:tv=F(1)
    header=schema.run_record(prepared,samples,seed,tv,budget=w) if original_header is None else original_header
    header_json=schema.canonical(header)
    if original_header is None:
        # Reproduce canonical reader ingestion before RNG. Allocation bounds alone
        # cannot certify that expensive coprime rational normalizations fit.
        decoded=decode_json(header_json.encode('utf-8'),integer_digits=20,
                            budget=WorkBudget(stage='reader-json-preflight'))
        reader_model=Model.from_dict(decoded['model'],_budget=WorkBudget(stage='reader-model-preflight'))
        BridgeRequest.from_dict(decoded['request'],reader_model,
                                _budget=WorkBudget(stage='reader-request-preflight'))
        del decoded,reader_model
    run=RunMetadata(seed,samples,header['run_hash'],header_json)
    longest=max(prepared.model.states,key=len);cnt=min(K,n*(n-1))
    time_text=_rational_prototype(time_bits,den_bits,True)
    duration_text=_rational_prototype(occ_bits,occ_den_bits)
    sample=dict(record_type='sample',sample_id=samples-1,start=prepared.request.start,end=prepared.request.end,
                t0=header['request']['t0'],t1=header['request']['t1'],uniformization_count=K,real_event_count=K,
                occupation=[{'state':longest,'duration':duration_text} for _ in range(n)],
                transitions=[{'from':longest,'to':longest,'count':K} for _ in range(cnt)])
    event=dict(record_type='event',sample_id=samples-1,event_index=max(0,K-1),uniformization_ordinal=K,
               **{'from':longest},to=longest,bin=M-1,time=time_text)
    footer=schema.complete_record(samples,samples*K,run.run_hash)
    json_lengths=[len(schema.json_line(record).encode('utf-8')) for record in (header,sample,event,footer)]
    csv_lengths=[len(schema.csv_line(record).encode('utf-8')) for record in (header,sample,event,footer)]
    json_total=json_lengths[0]+samples*json_lengths[1]+samples*K*json_lengths[2]+json_lengths[3]
    csv_total=len(schema.csv_header())+csv_lengths[0]+samples*csv_lengths[1]+samples*K*csv_lengths[2]+csv_lengths[3]
    output_bytes=max(json_total,csv_total);line_bytes=max(json_lengths+csv_lengths)
    _limit(output_bytes,limits.max_output_bytes,'output_bytes');_limit(line_bytes,limits.max_record_bytes,'record_bytes')
    time_size=128+int_bytes(time_bits)+int_bytes(den_bits)
    occ_size=128+int_bytes(occ_bits)+int_bytes(occ_den_bits)
    event_size=128+7*16+6*int_bytes(64)+time_size
    transition_size=tuple_bytes(3)+3*int_bytes(64)
    history_size=128+6*16+3*int_bytes(64)+tuple_bytes(K)+K*event_size+tuple_bytes(n)+n*occ_size+tuple_bytes(cnt)+cnt*transition_size
    model_size=tuple_bytes(n)+sum(64+len(label) for label in prepared.model.states)+tuple_bytes(len(prepared.model.edges))+sum(176+rational_bytes(e.rate) for e in prepared.model.edges)
    scratch=4*tuple_bytes(K+1)+2*(K+1)*int_bytes(64)+4*(time_size+occ_size+len(time_text)+len(duration_text))+4096
    base=32768+model_size+len(header_json)*2+sum(rational_bytes(v) for v in (prepared.certificate.retained,prepared.certificate.tail_upper,prepared.certificate.tv_upper))+scratch
    batch_bytes=base+tuple_bytes(samples)+samples*history_size
    reader_bytes=batch_bytes+256+128*max(json_lengths)
    _limit(batch_bytes,limits.max_batch_bytes,'batch_logical_bytes');_limit(reader_bytes,limits.max_reader_bytes,'reader_logical_bytes')
    return BatchBounds(samples,seed,grid,batch_bytes,output_bytes,reader_bytes,line_bytes,run)


def project_history(sample_id,states,bins,grid,nstates):
    events=[];ticks=[0]*nstates;counts={};state=states[0];previous_bin=0
    for ordinal,(old,new,bin_) in enumerate(zip(states,states[1:],bins),1):
        if old!=new:
            ticks[state]+=bin_-previous_bin
            events.append(Event(len(events),ordinal,old,new,bin_,grid.time(bin_)))
            counts[(old,new)]=counts.get((old,new),0)+1
            state=new;previous_bin=bin_
    ticks[state]+=(1<<grid.bits)-previous_bin
    occupations=tuple(F(grid.horizon.numerator*value,grid.tick_denominator) for value in ticks)
    transitions=tuple((i,j,count) for (i,j),count in sorted(counts.items()))
    return History(sample_id,len(bins),tuple(events),occupations,transitions)


def _sample_histories(prepared,bounds,source):
    histories=[];start=prepared.model.states.index(prepared.request.start)
    end=prepared.model.states.index(prepared.request.end);nstates=len(prepared.model.states)
    for sample_id in range(bounds.samples):
        count=choose(prepared.count_table,source);state=start;states=[state]
        for remaining in range(count,0,-1):
            table=prepared.step_tables[remaining][state]
            if table is None:raise InvariantError('Sample reached a zero-mass state')
            state=choose(table,source);states.append(state)
        if state!=end:raise InvariantError('Conditioned skeleton did not reach endpoint')
        bins=sorted(getbits(source,prepared.request.time_bits) for _ in range(count))
        histories.append(project_history(sample_id,states,bins,bounds.grid,nstates))
    return tuple(histories)


def sample_batch(prepared,*,samples,seed):
    bounds=preflight_batch(prepared,samples,seed)
    source=seeded_source(seed)
    histories=_sample_histories(prepared,bounds,source)
    return Batch(prepared.model,prepared.request,prepared.limits,prepared.certificate,bounds.run_metadata,histories)
