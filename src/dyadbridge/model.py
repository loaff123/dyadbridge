"""Canonical finite models and separate bridge/run options."""
from dataclasses import dataclass, InitVar
from fractions import Fraction
import json
import re
from .budget import WorkBudget, tuple_bytes, rational_bytes
from .errors import InputError
from .rational import parse_rational, format_rational, decimal_integer

LABEL = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,63}\Z')


def exact_fields(data, required, optional=()):
    if type(data) is not dict or set(data) - set(required) - set(optional) or set(required) - set(data):
        raise InputError('Object has missing or unknown fields')


def strict_integer(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise InputError(name + ' must be an integer in its allowed range', field=name)
    return value


def check_depth(text, max_depth=16):
    depth = 0; quoted = False; escaped = False
    for char in text:
        if quoted:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in '[{':
            depth += 1
            if depth > max_depth: raise InputError('JSON nesting depth exceeded')
        elif char in ']}': depth -= 1


def _pairs(pairs):
    data = {}
    for key, value in pairs:
        if key in data: raise InputError('Duplicate JSON key', field=key)
        data[key] = value
    return data


def _decoded_shape_bytes(text,max_depth,integer_digits):
    """Conservative logical JSON graph bound, before the decoder allocates it.

    Arrays reserve two slots per element. Objects reserve both the pairs-hook
    list/tuples and resulting dict (256 container bytes +208 per member).
    String payloads are covered by the caller's six-times-raw byte envelope;
    every string gets its 64-byte owner overhead. Scalar tokens reserve 256 bytes.
    Empty first-element slots deliberately overcount. No parser work is used
    to discover whether its own decoded graph fits.
    """
    size=0;stack=[];quoted=False;escaped=False;atom=False
    for char in text:
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
            continue
        if char.isspace():atom=False;continue
        if char=='"':size+=64;quoted=True;atom=False
        elif char in '[{':
            stack.append(char);atom=False
            if len(stack)>max_depth:raise InputError('JSON nesting depth exceeded')
            size+=160 if char=='[' else 464
        elif char in ']}':
            if stack:stack.pop()
            atom=False
        elif char==',':
            size+=208 if stack and stack[-1]=='{' else 32
            atom=False
        elif char==':':atom=False
        elif not atom:size+=256;atom=True
    return size


def decode_json(raw, *, max_depth=16, integer_digits=256, budget=None, owner=None):
    budget=budget or WorkBudget(stage="ingestion")
    budget.charge(2*len(raw))
    retained=owner is not None
    if owner is None:owner=('json-decode',budget._serial);budget._serial+=1
    budget.ledger.acquire(owner,5120+6*len(raw))
    successful=False
    try:
        text = raw.decode('utf-8')
        if text.startswith('\ufeff'):raise InputError('UTF-8 BOM is unsupported')
        budget.ledger.grow(owner,_decoded_shape_bytes(text,max_depth,integer_digits))
        def number(value):
            if len(value.lstrip('-')) > integer_digits:raise InputError('JSON integer token too long')
            return decimal_integer(value,max_bits=852 if integer_digits>20 else 67,budget=budget)
        def constant(value):raise InputError('JSON nonfinite values are unsupported')
        result=json.loads(text,object_pairs_hook=_pairs,parse_int=number,parse_constant=constant)
        successful=True
        return result
    except (UnicodeError,json.JSONDecodeError,RecursionError) as exc:
        raise InputError('Invalid bounded UTF-8 JSON') from exc
    finally:
        if not retained or not successful:budget.ledger.release(owner)


def parse_json_bounded(source, *, max_bytes=1048576, max_depth=16, budget=None, owner=None):
    budget=budget or WorkBudget(stage="ingestion")
    buffer_owner=('input-buffer',budget._serial);budget._serial+=1
    budget.ledger.acquire(buffer_owner,128+3*(max_bytes+1))
    try:
        raw=bytearray();total=0
        while True:
            chunk=source.read(max_bytes+1-total)
            if type(chunk) is not bytes:raise InputError('Expected a binary input stream')
            if not chunk:break
            total+=len(chunk)
            if total>max_bytes:raise InputError('Raw JSON input byte ceiling exceeded')
            raw.extend(chunk)
        return decode_json(bytes(raw),max_depth=max_depth,budget=budget,owner=owner)
    finally:budget.ledger.release(buffer_owner)


@dataclass(frozen=True)
class Edge:
    source: int
    destination: int
    rate: Fraction


@dataclass(frozen=True)
class Model:
    states: tuple
    edges: tuple
    _budget: InitVar[object] = None

    def __post_init__(self, _budget):
        budget=_budget or WorkBudget(stage="ingestion")
        if type(self.states) is not tuple or not 1 <= len(self.states) <= 64 or any(type(s) is not str or not LABEL.fullmatch(s) for s in self.states):
            raise InputError('Invalid canonical states')
        if self.states != tuple(sorted(set(self.states))): raise InputError('States must be unique and canonical')
        if type(self.edges) is not tuple or len(self.edges) > 4032: raise InputError('Invalid canonical edges')
        previous = (-1, -1)
        canonical_size=len('{"rates":[],"schema":"dyadbridge.model.v1","states":[]}')
        canonical_size+=sum(len(label)+2 for label in self.states)+max(0,len(self.states)-1)
        canonical_size+=max(0,len(self.edges)-1)
        for edge in self.edges:
            if type(edge) is not Edge or type(edge.source) is not int or type(edge.destination) is not int:
                raise InputError('Invalid canonical edge')
            pair = (edge.source, edge.destination)
            if not (0 <= pair[0] < len(self.states) and 0 <= pair[1] < len(self.states)) or pair[0] == pair[1] or pair <= previous:
                raise InputError('Edges must be distinct canonical off-diagonal entries')
            if type(edge.rate) is not Fraction or edge.rate.numerator <= 0 or max(edge.rate.numerator.bit_length(), edge.rate.denominator.bit_length()) > 512:
                raise InputError('Canonical rates must be positive bounded exact Fractions')
            spelling=format_rational(edge.rate,budget=budget)
            if len(spelling)>256:raise InputError('Canonical input rational exceeds 256 characters')
            canonical_size+=len('{"from":"","rate":"","to":""}')+len(self.states[pair[0]])+len(self.states[pair[1]])+len(spelling)
            if canonical_size>1048576:raise InputError('Canonical model exceeds its input byte envelope')
            previous = pair

    @classmethod
    def from_dict(cls, data, *, _budget=None):
        exact_fields(data, ('schema', 'states', 'rates'))
        if data['schema'] != 'dyadbridge.model.v1': raise InputError('Unsupported model schema')
        states, rates = data['states'], data['rates']
        if type(states) is not list or not 1 <= len(states) <= 64: raise InputError('State count must be in 1..64')
        if any(type(s) is not str or not LABEL.fullmatch(s) for s in states) or len(set(states)) != len(states):
            raise InputError('State labels must be unique ASCII identifiers')
        if type(rates) is not list or len(rates) > 4032: raise InputError('Too many or malformed rates')
        states = tuple(sorted(states)); indices = {s: i for i, s in enumerate(states)}
        budget = _budget or WorkBudget(stage='ingestion'); seen = set(); edges = []
        budget.ledger.acquire('states', tuple_bytes(len(states)) + sum(64 + len(s) for s in states))
        for record in rates:
            exact_fields(record, ('from', 'to', 'rate'))
            source, destination = record['from'], record['to']
            if type(source) is not str or type(destination) is not str or source not in indices or destination not in indices:
                raise InputError('Unknown rate endpoint')
            pair = (indices[source], indices[destination])
            if pair[0] == pair[1]: raise InputError('Supply off-diagonal rates only')
            if pair in seen: raise InputError('Duplicate directed rate')
            seen.add(pair)
            rate = parse_rational(record['rate'], budget=budget)
            if rate < 0: raise InputError('Rates must be nonnegative')
            if rate:
                budget.ledger.acquire(('rate', pair), 128 + 48 + rational_bytes(rate))
                edges.append(Edge(*pair, rate))
        return cls(states, tuple(sorted(edges, key=lambda e: (e.source, e.destination))), _budget=budget)

    def to_dict(self, *, budget=None):
        return {'schema':'dyadbridge.model.v1', 'states':list(self.states),
                'rates':[{'from':self.states[e.source], 'to':self.states[e.destination],
                          'rate':format_rational(e.rate,budget=budget)} for e in self.edges]}


def load_model(source):
    budget=WorkBudget(stage="ingestion")
    owner='decoded-model-input'
    data=parse_json_bounded(source,budget=budget,owner=owner)
    try:return Model.from_dict(data,_budget=budget)
    finally:budget.ledger.release(owner)


@dataclass(frozen=True)
class BridgeRequest:
    start: str
    end: str
    t0: Fraction
    t1: Fraction
    epsilon: Fraction = Fraction(1, 10**12)
    time_bits: int = 32
    _budget: InitVar[object] = None

    def __post_init__(self, _budget):
        budget=_budget or WorkBudget(stage="ingestion")
        if any(type(x) is not str or not LABEL.fullmatch(x) for x in (self.start,self.end)):
            raise InputError('Invalid endpoint labels')
        for value in (self.t0,self.t1,self.epsilon):
            if type(value) is not Fraction or max(abs(value.numerator).bit_length(),value.denominator.bit_length()) > 512:
                raise InputError('Request values must be bounded exact Fractions')
            if len(format_rational(value,budget=budget))>256:raise InputError('Canonical request rational exceeds 256 characters')
        if not budget.qle(self.t0,self.t1): raise InputError('Negative horizon')
        if not 0 < self.epsilon.numerator < self.epsilon.denominator: raise InputError('Invalid epsilon')
        strict_integer(self.time_bits,1,64,'time_bits')

    @classmethod
    def from_dict(cls, data, model, *, _budget=None):
        exact_fields(data, ('start','end','t0','t1'), ('epsilon','time_bits'))
        if type(data['start']) is not str or type(data['end']) is not str or data['start'] not in model.states or data['end'] not in model.states:
            raise InputError('Unknown bridge endpoint')
        budget = _budget or WorkBudget(stage='ingestion')
        t0=parse_rational(data['t0'], budget=budget); t1=parse_rational(data['t1'], budget=budget)
        epsilon=parse_rational(data.get('epsilon','1/1000000000000'), budget=budget)
        if not budget.qle(t0,t1): raise InputError('t1 must be at least t0')
        if not 0 < epsilon < 1: raise InputError('epsilon must be strictly between 0 and 1')
        bits=strict_integer(data.get('time_bits',32),1,64,'time_bits')
        return cls(data['start'],data['end'],t0,t1,epsilon,bits,_budget=budget)

    def to_dict(self, *, budget=None):
        return {'start':self.start,'end':self.end,'t0':format_rational(self.t0,budget=budget),'t1':format_rational(self.t1,budget=budget),
                'epsilon':format_rational(self.epsilon,budget=budget),'time_bits':self.time_bits}


@dataclass(frozen=True)
class RunOptions:
    samples: int
    seed: int
    format: str = 'jsonl'
    output: str | None = None
    overwrite: bool = False

    def __post_init__(self):
        strict_integer(self.seed,0,2**64-1,'seed')
        strict_integer(self.samples,1,10000,'samples')
        if self.format not in ('jsonl','csv') or (self.output is not None and type(self.output) is not str) or type(self.overwrite) is not bool:
            raise InputError('Invalid delivery options')

    @classmethod
    def from_dict(cls, data):
        exact_fields(data,('seed',),('samples','format','output','overwrite'))
        seed=strict_integer(data['seed'],0,2**64-1,'seed')
        samples=strict_integer(data.get('samples',1),1,10000,'samples')
        format_=data.get('format','jsonl'); output=data.get('output'); overwrite=data.get('overwrite',False)
        if format_ not in ('jsonl','csv') or (output is not None and type(output) is not str) or type(overwrite) is not bool:
            raise InputError('Invalid delivery options')
        return cls(samples,seed,format_,output,overwrite)
