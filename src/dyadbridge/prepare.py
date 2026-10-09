"""Standard uniformization with deterministic bounded all-integer preparation."""
from dataclasses import dataclass
from fractions import Fraction as F
from .budget import Limits, WorkBudget, int_bytes, tuple_bytes, rational_bytes
from .errors import InputError, ImpossibleEndpoint, ResourceLimitError, InvariantError
from .model import Model, BridgeRequest


@dataclass(frozen=True)
class Categorical:
    outcomes: tuple
    cumulative: tuple

    @property
    def total(self):
        return self.cumulative[-1]


@dataclass(frozen=True)
class Certificate:
    method: str
    lambda_: F
    mu: F
    cutoff: int
    retained: F
    tail_upper: F
    tv_upper: F
    epsilon: F
    time_bits: int
    time_displacement: F


@dataclass(frozen=True)
class PreparationDiagnostics:
    work_units: int
    peak_logical_bytes: int
    categorical_entries: int
    max_integer_bits: int
    kernel_denominator_bits: int

    def to_dict(self):
        return dict(work_units=self.work_units,peak_logical_bytes=self.peak_logical_bytes,
                    categorical_entries=self.categorical_entries,max_integer_bits=self.max_integer_bits,
                    kernel_denominator_bits=self.kernel_denominator_bits)


@dataclass(frozen=True)
class PreparedBridge:
    model: Model
    request: BridgeRequest
    limits: Limits
    certificate: Certificate
    kernel_rows: tuple
    backward: tuple
    count_table: Categorical
    step_tables: tuple
    preparation_diagnostics: PreparationDiagnostics


def _limit(value, ceiling, name, stage='preparation'):
    if value > ceiling:
        raise ResourceLimitError('Preparation ceiling exceeded',stage=stage,limit=name,ceiling=ceiling,predicted=value)


def _reachable(model, start, end):
    rows=[[] for _ in model.states]
    for edge in model.edges: rows[edge.source].append(edge.destination)
    seen={start}; todo=[start]
    while todo:
        for j in rows[todo.pop()]:
            if j not in seen: seen.add(j); todo.append(j)
    return end in seen


def prepare(model, request, *, limits=Limits()):
    """Prepare every possible categorical before any model RNG is constructed.

    A resource refusal is deterministic and never returns a partial sampler.
    """
    if type(model) is not Model or type(request) is not BridgeRequest or type(limits) is not Limits:
        raise InputError('Expected validated Model, BridgeRequest and Limits values')
    if request.start not in model.states or request.end not in model.states:
        raise InputError('Request endpoints do not belong to this model')
    n=len(model.states); a=model.states.index(request.start); b=model.states.index(request.end)
    _limit(n,limits.max_states,'states'); _limit(len(model.edges),limits.max_edges,'edges')
    budget=WorkBudget(limits)
    for value in (request.t0,request.t1,request.epsilon):
        budget.bits(value.numerator);budget.bits(value.denominator)
    for edge in model.edges:
        budget.bits(edge.rate.numerator);budget.bits(edge.rate.denominator)
    budget.ledger.acquire('model',tuple_bytes(n)+sum(64+len(s) for s in model.states)+tuple_bytes(len(model.edges))+
                          sum(176+rational_bytes(e.rate) for e in model.edges))
    budget.ledger.acquire('request',512+sum(rational_bytes(v) for v in (request.t0,request.t1,request.epsilon)))
    # Graph storage is bounded before creating its lists/sets.
    budget.ledger.acquire('reachability',512+4*tuple_bytes(n)+2*tuple_bytes(len(model.edges)))
    if request.t0 == request.t1:
        if a != b: raise ImpossibleEndpoint('Different states at a zero horizon are impossible')
    elif not _reachable(model,a,b):
        raise ImpossibleEndpoint('Endpoint is unreachable along positive-rate edges')
    budget.ledger.release('reachability')
    horizon=budget.qadd(request.t1,budget.fraction(-request.t0.numerator,request.t0.denominator))
    # A conservative whole-row reservation permits every checked rational sum.
    frac_ceiling=128+2*int_bytes(limits.max_integer_bits)
    budget.ledger.acquire('exits',2*tuple_bytes(n)+n*frac_ceiling)
    exits=[F(0) for _ in range(n)]
    for edge in model.edges: exits[edge.source]=budget.qadd(exits[edge.source],edge.rate)
    rate=F(0)
    for value in exits:
        if not budget.qle(value,rate): rate=value
    mu=budget.qmul(rate,horizon)
    if not budget.qle(mu,F(limits.max_mu)):
        raise ResourceLimitError('Uniformization mean exceeds ceiling',stage='preparation',
                                 limit='mu',ceiling=limits.max_mu,predicted=mu)
    displacement=budget.qdiv(horizon,F(1<<request.time_bits))
    budget.ledger.acquire('scalar-cache',32*int_bytes(limits.max_integer_bits)+12*128)

    if horizon == 0 or rate == 0:
        if a != b: raise ImpossibleEndpoint('Zero generator cannot connect different states')
        cert=Certificate('deterministic-zero-horizon' if horizon==0 else 'deterministic-zero-generator',
                         rate,mu,0,F(1),F(0),F(0),request.epsilon,request.time_bits,displacement)
        budget.ledger.acquire('trivial',2048+4*tuple_bytes(n))
        budget.ledger.release('exits')
        diagnostics=PreparationDiagnostics(budget.work_units,budget.ledger.peak,1,budget.max_seen_bits,0)
        return PreparedBridge(model,request,limits,cert,(),(tuple(int(i==b) for i in range(n)),),
                              Categorical((0,),(1,)),(tuple(None for _ in range(n)),),diagnostics)

    # Reserve every rational R cell before constructing it, then discard R after A.
    r_slots=len(model.edges)+n
    budget.ledger.acquire('rational-kernel',4*tuple_bytes(n)+r_slots*(frac_ceiling+256))
    edge_rows=[[] for _ in range(n)]
    for edge in model.edges: edge_rows[edge.source].append(edge)
    rational_rows=[]; D=1
    for i in range(n):
        row=[(edge.destination,budget.qdiv(edge.rate,rate)) for edge in edge_rows[i]]
        diagonal=budget.qadd(F(1),budget.qdiv(budget.fraction(-exits[i].numerator,exits[i].denominator),rate))
        if diagonal: row.append((i,diagonal))
        row.sort(key=lambda item:item[0])
        for _,p in row:
            D=budget.lcm(D,p.denominator)
            _limit(D.bit_length(),limits.max_denominator_bits,'kernel_denominator_bits')
        rational_rows.append(row)
    budget.ledger.acquire('integer-kernel',2*tuple_bytes(n)+r_slots*(320+int_bytes(D.bit_length())))
    rows=[]
    for row in rational_rows:
        entries=tuple((j,budget.mul(p.numerator,budget.div(D,p.denominator))) for j,p in row)
        total=0
        for _,value in entries: total=budget.add(total,value)
        if total != D: raise InvariantError('Uniformization row does not sum to denominator')
        rows.append(entries)
    rows=tuple(rows)
    del rational_rows,edge_rows,exits
    budget.ledger.release('rational-kernel');budget.ledger.release('exits')
    x=budget.qdiv(mu,F(D)); U,V=x.numerator,x.denominator
    DU=budget.mul(D,U); epsilon_p=request.epsilon.numerator
    epsilon_slack=budget.add(request.epsilon.denominator,-epsilon_p)
    budget.ledger.acquire('backward-outer',2*tuple_bytes(limits.max_cutoff+1))
    budget.ledger.acquire(('beta',0),2*tuple_bytes(n)+n*int_bytes(1))
    backward=[tuple(int(i==b) for i in range(n))]
    C=backward[0][a]; power_u=1; power_du=DU; power_v=1; fact=1
    for k in range(limits.max_cutoff+1):
        gap=budget.add(budget.mul(V,k+2),-DU)
        if C > 0 and gap > 0:
            tail_numerator=budget.mul(power_du,k+2)
            retained_scaled=budget.mul(budget.mul(C,k+1),gap)
            left=budget.mul(epsilon_slack,tail_numerator)
            right=budget.mul(epsilon_p,retained_scaled)
            if left <= right: break
        if k == limits.max_cutoff:
            raise ResourceLimitError('No certified cutoff within the event ceiling',stage='preparation',limit='cutoff',
                                     ceiling=limits.max_cutoff,predicted=k+1)
        r=k+1
        beta_bits=1 if D==1 else r*D.bit_length()+1
        budget.check_bits(beta_bits)
        budget.ledger.acquire(('beta',r),2*tuple_bytes(n)+n*int_bytes(beta_bits))
        vector=[]
        for row in rows:
            value=0
            for j,weight in row: value=budget.add(value,budget.mul(weight,backward[-1][j]))
            vector.append(value)
        backward.append(tuple(vector))
        power_u=budget.mul(power_u,U)
        C=budget.add(budget.mul(budget.mul(V,r),C),budget.mul(power_u,backward[-1][a]))
        power_du=budget.mul(power_du,DU)
        power_v=budget.mul(power_v,V);fact=budget.mul(fact,r)

    base_denominator=budget.mul(power_v,fact)
    retained=budget.fraction(C,base_denominator)
    tail=budget.fraction(tail_numerator,budget.mul(budget.mul(base_denominator,k+1),gap))
    delta=budget.fraction(tail_numerator,budget.add(tail_numerator,retained_scaled))
    cert=Certificate('integer-uniformization-v1',rate,mu,k,retained,tail,delta,
                     request.epsilon,request.time_bits,displacement)
    budget.ledger.acquire('row-working-containers', 1024+8*tuple_bytes(n)+n*tuple_bytes(2))
    entries_count=0

    def categorical(outcomes, masses, owner, total_bound):
        nonlocal entries_count
        entries_count += len(outcomes)
        _limit(entries_count,limits.max_entries,'categorical_entries')
        budget.ledger.acquire(owner,512+4*tuple_bytes(len(outcomes))+len(outcomes)*int_bytes(max(1,total_bound.bit_length())))
        cumulative=[];total=0
        for value in masses:
            total=budget.add(total,value);cumulative.append(total)
        if not total or not cumulative: raise InvariantError('Empty positive categorical table')
        return Categorical(tuple(outcomes),tuple(cumulative))

    budget.ledger.acquire('count-scratch',2*tuple_bytes(k+1)+(k+1)*int_bytes(C.bit_length()))
    weights=[0]*(k+1); coefficient=power_u
    for index in range(k,-1,-1):
        weights[index]=budget.mul(coefficient,backward[index][a])
        if index:
            numerator=budget.mul(budget.mul(coefficient,V),index)
            coefficient=budget.div(numerator,U)
            if budget.mul(coefficient,U) != numerator: raise InvariantError('Inexact count coefficient division')
    outcomes=tuple(i for i,w in enumerate(weights) if w)
    count_table=categorical(outcomes,(weights[i] for i in outcomes),'count-table',C)
    if count_table.total != C: raise InvariantError('Count integer normalizer mismatch')
    del weights
    budget.ledger.release('count-scratch')
    budget.ledger.acquire('step-outer',2*tuple_bytes(k+1)+(k+1)*2*tuple_bytes(n))
    step_tables=[tuple(None for _ in range(n))]
    for r in range(1,k+1):
        step_row=[]
        for i in range(n):
            total=backward[r][i]
            if not total:
                step_row.append(None);continue
            choices=tuple((j,weight) for j,weight in rows[i] if backward[r-1][j])
            # Reserve full categorical storage before constructing any products.
            table=categorical(tuple(j for j,_ in choices),
                              (budget.mul(weight,backward[r-1][j]) for j,weight in choices),
                              ('step',r,i),total)
            if table.total != total:raise InvariantError('Backward transition normalizer mismatch')
            step_row.append(table)
        step_tables.append(tuple(step_row))
    diagnostics=PreparationDiagnostics(budget.work_units,budget.ledger.peak,entries_count,budget.max_seen_bits,D.bit_length())
    return PreparedBridge(model,request,limits,cert,rows,tuple(backward),count_table,tuple(step_tables),diagnostics)
