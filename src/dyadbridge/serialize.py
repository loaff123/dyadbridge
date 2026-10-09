"""Bounded event-format readback, not a provenance or sampling-law verifier."""
from contextlib import contextmanager
from fractions import Fraction as F
import json
import re
from types import SimpleNamespace
from . import schema
from .budget import Limits,LogicalLedger
from .errors import InputError,ResourceLimitError
from .model import Model,BridgeRequest,exact_fields,strict_integer,decode_json
from .prepare import Certificate,PreparationDiagnostics
from .rational import decimal_integer,format_rational
from .sample import Batch,Event,History,RunMetadata,_preflight_metadata,project_history

RUN_FIELDS=('record_type','schema','package_version','algorithm','rng','runtime','model','request','limits',
            'model_hash','request_hash','run_hash','seed','sample_count','certificate','preparation')
SAMPLE_FIELDS=('record_type','sample_id','start','end','t0','t1','uniformization_count','real_event_count','occupation','transitions')
EVENT_FIELDS=('record_type','sample_id','event_index','uniformization_ordinal','from','to','bin','time')
CERT_FIELDS=('method','target_law','lambda','mu','cutoff','retained_mass','tail_upper','tv_upper','epsilon','time_bits',
             'strict_time_displacement_upper','batch_tv_upper','randomness_assumption','model_assumption')
PREPARATION_FIELDS=('work_units','peak_logical_bytes','categorical_entries','max_integer_bits','kernel_denominator_bits')
RAT=re.compile(r'-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?\Z')


def _body_records(batch):
    for history in batch.histories:
        yield schema.sample_record(batch.model,batch.request,history)
        for event in history.events:yield schema.event_record(batch.model,history.sample_id,event)
    yield schema.complete_record(len(batch.histories),sum(len(h.events) for h in batch.histories),batch.run_metadata.run_hash)


def to_jsonl(batch):
    yield batch.run_metadata.header_json+'\n'
    for record in _body_records(batch):yield schema.json_line(record)


def to_csv(batch):
    yield schema.csv_header()
    yield schema.csv_line(json.loads(batch.run_metadata.header_json))
    for record in _body_records(batch):yield schema.csv_line(record)


def _fraction(text):
    if type(text) is not str or len(text)>19733 or not RAT.fullmatch(text):raise InputError('Invalid bounded output rational',stage='readback')
    parts=text.split('/')
    n=decimal_integer(parts[0],max_bits=32768)
    d=decimal_integer(parts[1],max_bits=32768) if len(parts)==2 else 1
    value=F(n,d)
    if format_rational(value)!=text:raise InputError('Output rational is not canonical',stage='readback')
    return value


def _require(condition,message):
    if not condition:raise InputError(message,stage='readback')


class _Reader:
    def __init__(self,source):
        self.source=source;self.total=0;self.records=0
        self.max_total=268435456;self.max_line=8388608
        self.ledger=LogicalLedger(536870912,'readback')

    @contextmanager
    def record(self):
        raw=self.source.readline(self.max_line+1)
        if type(raw) is not bytes:raise InputError('Expected binary JSONL stream',stage='readback')
        if not raw:raise InputError('Incomplete JSONL: expected another record',stage='readback')
        self.total+=len(raw);self.records+=1
        if len(raw)>self.max_line or self.total>self.max_total or self.records>1010002:
            raise ResourceLimitError('JSONL stream envelope exceeded',stage='readback')
        if not raw.endswith(b'\n') or raw==b'\n':raise InputError('Each JSONL record requires a final LF',stage='readback')
        owner=('decode',self.records)
        self.ledger.acquire(owner,256+128*len(raw))
        try:
            record=decode_json(raw,integer_digits=20)
            if type(record) is not dict:raise InputError('Expected JSONL object record',stage='readback')
            yield record
        finally:self.ledger.release(owner)

    def finish(self):
        if self.source.read(1)!=b'':raise InputError('Trailing data after completion record',stage='readback')


def _parse_header(header):
    exact_fields(header,RUN_FIELDS)
    _require(header['record_type']=='run','First record must be run')
    for key,value in [('schema',schema.SCHEMA),('package_version',schema.VERSION),('algorithm',schema.ALGORITHM),('rng',schema.RNG)]:
        _require(header[key]==value,'Unsupported '+key)
    exact_fields(header['runtime'],('implementation','version'))
    _require(all(type(x) is str and 0<len(x)<=128 for x in header['runtime'].values()),'Invalid runtime metadata')
    model=Model.from_dict(header['model']);_require(model.to_dict()==header['model'],'Model is not canonical')
    request=BridgeRequest.from_dict(header['request'],model);_require(request.to_dict()==header['request'],'Request is not canonical')
    exact_fields(header['limits'],Limits().to_dict())
    limits=Limits(**header['limits'])
    samples=strict_integer(header['sample_count'],1,limits.max_samples,'sample_count')
    seed_text=header['seed'];_require(type(seed_text) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}',seed_text) is not None,'Invalid seed string')
    seed=decimal_integer(seed_text,max_bits=64);strict_integer(seed,0,2**64-1,'seed')
    exact_fields(header['certificate'],CERT_FIELDS);data=header['certificate']
    _require(data['target_law']==schema.TARGET and data['randomness_assumption']=='independent-unbiased-bits' and data['model_assumption']=='supplied-rational-generator','Unsupported certificate contract')
    _require(data['method'] in ('integer-uniformization-v1','deterministic-zero-horizon','deterministic-zero-generator'),'Unknown certificate method')
    cutoff=strict_integer(data['cutoff'],0,limits.max_cutoff,'cutoff')
    bits=strict_integer(data['time_bits'],1,64,'time_bits')
    vals={name:_fraction(data[name]) for name in ('lambda','mu','retained_mass','tail_upper','tv_upper','epsilon','strict_time_displacement_upper','batch_tv_upper')}
    _require(all(value>=0 for key,value in vals.items()),'Negative certificate quantity')
    quotient,remainder=divmod(vals['mu'].numerator,vals['mu'].denominator)
    _require(quotient<limits.max_mu or (quotient==limits.max_mu and remainder==0),'Declared mu exceeds envelope')
    _require(vals['retained_mass']>0 and vals['tv_upper']<=request.epsilon,'Invalid retained mass or claimed bound')
    _require(vals['epsilon']==request.epsilon and bits==request.time_bits,'Certificate/request mismatch')
    _require(vals['batch_tv_upper']==min(F(1),samples*vals['tv_upper']),'Batch bound mismatch')
    _require(vals['strict_time_displacement_upper']==(request.t1-request.t0)/(1<<bits),'Grid displacement mismatch')
    if data['method']=='deterministic-zero-horizon':_require(request.t0==request.t1 and request.start==request.end,'Zero-horizon method contradicts observations')
    if data['method']=='deterministic-zero-generator':_require(not model.edges and request.start==request.end,'Zero-generator method contradicts model')
    if data['method'].startswith('deterministic'):
        _require(cutoff==0 and vals['retained_mass']==1 and vals['tail_upper']==0 and vals['tv_upper']==0,'Invalid deterministic certificate')
    certificate=Certificate(data['method'],vals['lambda'],vals['mu'],cutoff,vals['retained_mass'],vals['tail_upper'],vals['tv_upper'],vals['epsilon'],bits,vals['strict_time_displacement_upper'])
    exact_fields(header['preparation'],PREPARATION_FIELDS)
    ceilings=(limits.max_work,limits.max_prepared_bytes,limits.max_entries,limits.max_integer_bits,limits.max_denominator_bits)
    values=[strict_integer(header['preparation'][key],0,ceiling,key) for key,ceiling in zip(PREPARATION_FIELDS,ceilings)]
    diagnostics=PreparationDiagnostics(*values)
    mh=schema.identity(model.to_dict());rh=schema.identity({'model_hash':mh,'request':request.to_dict(),'limits':limits.to_dict()})
    run_hash=schema.identity({'request_hash':rh,'seed':seed_text,'sample_count':samples,'package_version':schema.VERSION,'algorithm':schema.ALGORITHM,'rng':schema.RNG,'schema':schema.SCHEMA})
    _require((header['model_hash'],header['request_hash'],header['run_hash'])==(mh,rh,run_hash),'Input/run identity hash mismatch')
    metadata=SimpleNamespace(model=model,request=request,limits=limits,certificate=certificate,preparation_diagnostics=diagnostics)
    bounds=_preflight_metadata(metadata,samples,seed,original_header=header)
    return model,request,limits,certificate,bounds


def read_jsonl(source):
    """Read this version's bounded format; hashes do not authenticate events.

    Re-preparation can check a deterministic certificate; seeded replay is a
    separate operation. This reader performs neither of those operations.
    """
    reader=_Reader(source)
    with reader.record() as header:
        model,request,limits,certificate,bounds=_parse_header(header)
    del header
    reader.max_total=limits.max_output_bytes;reader.max_line=limits.max_record_bytes
    reader.ledger=LogicalLedger(limits.max_reader_bytes,'readback')
    reader.ledger.acquire('materialized-batch',bounds.batch_bytes)
    states={label:i for i,label in enumerate(model.states)}
    histories=[];total_events=0;K=certificate.cutoff;M=1<<request.time_bits
    for sample_id in range(bounds.samples):
        with reader.record() as record:
            exact_fields(record,SAMPLE_FIELDS)
            _require(record['record_type']=='sample','Expected sample header')
            _require(type(record['sample_id']) is int and record['sample_id']==sample_id,'Nonsequential sample id')
            _require((record['start'],record['end'],record['t0'],record['t1'])==(request.start,request.end,format_rational(request.t0),format_rational(request.t1)),'Sample observation mismatch')
            N=strict_integer(record['uniformization_count'],0,K,'uniformization_count')
            J=strict_integer(record['real_event_count'],0,N,'real_event_count')
            _require(type(record['occupation']) is list and len(record['occupation'])==len(model.states),'Invalid occupation vector')
            occupation=[]
            for label,item in zip(model.states,record['occupation']):
                exact_fields(item,('state','duration'));_require(item['state']==label,'Noncanonical occupation order')
                duration=_fraction(item['duration']);_require(duration>=0,'Negative occupation');occupation.append(duration)
            _require(type(record['transitions']) is list and len(record['transitions'])<=min(J,len(states)*(len(states)-1)),'Invalid transition counts')
            transitions=[]
            for item in record['transitions']:
                exact_fields(item,('from','to','count'))
                _require(type(item['from']) is str and type(item['to']) is str and item['from'] in states and item['to'] in states and item['from']!=item['to'],'Invalid directed count')
                transitions.append((states[item['from']],states[item['to']],strict_integer(item['count'],1,J,'transition count')))
            _require(tuple(transitions)==tuple(sorted(set(transitions))),'Transition counts must be canonical')
            occupation=tuple(occupation);transitions=tuple(transitions)
        del record
        events=[];path=[states[request.start]];bins=[];last_ordinal=0
        for index in range(J):
            with reader.record() as record:
                exact_fields(record,EVENT_FIELDS);_require(record['record_type']=='event','Expected event')
                _require(type(record['sample_id']) is int and type(record['event_index']) is int and record['sample_id']==sample_id and record['event_index']==index,'Event index mismatch')
                ordinal=strict_integer(record['uniformization_ordinal'],last_ordinal+1,N,'uniformization_ordinal')
                bin_=strict_integer(record['bin'],0,M-1,'bin')
                _require(not bins or bin_>=bins[-1],'Event bins are not sorted')
                _require(type(record['from']) is str and type(record['to']) is str and record['from'] in states and record['to'] in states,'Unknown event state')
                old,new=states[record['from']],states[record['to']]
                _require(old==path[-1] and new!=old,'Broken real-event chain')
                time=_fraction(record['time']);_require(time==bounds.grid.time(bin_),'Bin/time mismatch')
                events.append(Event(index,ordinal,old,new,bin_,time));path.append(new);bins.append(bin_);last_ordinal=ordinal
            del record
        _require(path[-1]==states[request.end],'History does not reach observed endpoint')
        check=project_history(sample_id,path,bins,bounds.grid,len(states))
        _require(occupation==check.occupation and transitions==check.transitions,'Quantized summary mismatch')
        histories.append(History(sample_id,N,tuple(events),occupation,transitions));total_events+=J
    with reader.record() as footer:
        exact_fields(footer,('record_type','sample_count','event_count','run_hash'))
        strict_integer(footer['sample_count'],1,limits.max_samples,'sample_count')
        strict_integer(footer['event_count'],0,limits.max_events,'event_count')
        _require(footer==schema.complete_record(bounds.samples,total_events,bounds.run_metadata.run_hash),'Completion footer mismatch')
    del footer
    reader.finish()
    return Batch(model,request,limits,certificate,bounds.run_metadata,tuple(histories))
