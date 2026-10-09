"""Deterministic abstract-work and logical-allocation guards.

These are portable representation bounds, not OS RSS or elapsed-time limits.
Sampling never consults these guards after it begins drawing model randomness.
"""
from dataclasses import dataclass, fields
from functools import wraps
from contextlib import contextmanager
from fractions import Fraction
from .errors import InputError, ResourceLimitError


@dataclass(frozen=True)
class Limits:
    max_states: int = 64
    max_edges: int = 4032
    max_denominator_bits: int = 512
    max_mu: int = 64
    max_cutoff: int = 256
    max_integer_bits: int = 32768
    max_entries: int = 262144
    max_prepared_bytes: int = 67108864
    max_work: int = 4294967296
    max_samples: int = 10000
    max_events: int = 1000000
    max_draws: int = 2000000
    max_output_bytes: int = 268435456
    max_batch_bytes: int = 134217728
    max_reader_bytes: int = 536870912
    max_record_bytes: int = 8388608

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            minimum = 0 if field.name == 'max_cutoff' else 1
            if type(value) is not int or not minimum <= value <= field.default:
                raise InputError('Limit cannot exceed its hard ceiling or use a noninteger value', limit=field.name)

    def to_dict(self):
        return {field.name: getattr(self, field.name) for field in fields(self)}


def int_bytes(bits):
    return 64 + 8 * ((max(1, bits) + 63) // 64)


def tuple_bytes(length):
    return 128 + 16 * length


def rational_bytes(value):
    return 128 + int_bytes(value.numerator.bit_length()) + int_bytes(value.denominator.bit_length())


class LogicalLedger:
    def __init__(self, limit, stage='preparation'):
        self.limit, self.stage = limit, stage
        self.current = self.peak = 0
        self._owners = {}

    def acquire(self, owner, size):
        if owner in self._owners:
            raise ValueError('Logical owner already reserved')
        if type(size) is not int or size < 0:
            raise ValueError('Invalid logical reservation')
        if self.current + size > self.limit:
            raise ResourceLimitError('Logical allocation ceiling exceeded', stage=self.stage,
                                     limit='logical_bytes', ceiling=self.limit, predicted=self.current + size)
        self._owners[owner] = size
        self.current += size
        self.peak = max(self.peak, self.current)

    def grow(self, owner, extra):
        if type(extra) is not int or extra<0:raise ValueError('Invalid logical growth')
        if self.current+extra>self.limit:
            raise ResourceLimitError('Logical allocation ceiling exceeded',stage=self.stage,
                                     limit='logical_bytes',ceiling=self.limit,predicted=self.current+extra)
        self._owners[owner]+=extra
        self.current+=extra
        self.peak=max(self.peak,self.current)

    def release(self, owner):
        self.current -= self._owners.pop(owner)


def _compound(integer_slots):
    """Reserve all overlapping returned temporaries of a compound helper.

    Slots are conservative maximum-width scratch owners, independent of object
    identity; the caller separately owns retained inputs and returned values.
    """
    def decorate(method):
        @wraps(method)
        def guarded(self, *args, **kwargs):
            owner = ('compound', self._serial)
            self._serial += 1
            self.ledger.acquire(owner, 128 + integer_slots * int_bytes(self.limits.max_integer_bits))
            try:
                return method(self, *args, **kwargs)
            finally:
                self.ledger.release(owner)
        return guarded
    return decorate


class WorkBudget:
    def __init__(self, limits=None, *, stage='preparation'):
        self.limits = limits or Limits()
        self.stage = stage
        self.work_units = self.max_seen_bits = 0
        self.ledger = LogicalLedger(self.limits.max_prepared_bytes, stage)
        self._serial = 0

    @contextmanager
    def scratch(self, integer_slots, bits, extra_bytes=0):
        self.check_bits(bits)
        owner=('caller-scratch',self._serial);self._serial+=1
        self.ledger.acquire(owner,128+integer_slots*int_bytes(bits)+extra_bytes)
        try:yield
        finally:self.ledger.release(owner)

    def charge(self, units):
        if self.work_units + units > self.limits.max_work:
            raise ResourceLimitError('Exact-arithmetic work ceiling exceeded', stage=self.stage,
                                     limit='work_units', ceiling=self.limits.max_work,
                                     predicted=self.work_units + units)
        self.work_units += units

    def bits(self, value):
        size = max(1, abs(value).bit_length())
        self.check_bits(size)
        self.max_seen_bits = max(self.max_seen_bits, size)
        return size

    def check_bits(self, size):
        if size > self.limits.max_integer_bits:
            raise ResourceLimitError('Integer growth ceiling exceeded before arithmetic', stage=self.stage,
                                     limit='integer_bits', ceiling=self.limits.max_integer_bits, predicted=size)

    def _calculate(self, bound, cost, operation):
        self.check_bits(bound)
        self.charge(cost)
        owner = ('scratch', self._serial); self._serial += 1
        self.ledger.acquire(owner, int_bytes(bound))
        try:
            result = operation()
            self.bits(result)
            return result
        finally:
            self.ledger.release(owner)

    def add(self, a, b):
        p, q = self.bits(a), self.bits(b)
        if a == 0 or b == 0:
            return self._calculate(max(p, q), 1, lambda: a + b)
        return self._calculate(max(p, q) + 1, max(p, q) + 1, lambda: a + b)

    def mul(self, a, b):
        p, q = self.bits(a), self.bits(b)
        if a == 0 or b == 0:
            return self._calculate(1, 1, lambda: 0)
        if abs(a) == 1 or abs(b) == 1:
            return self._calculate(max(p, q), 1, lambda: a * b)
        return self._calculate(p + q, p * q, lambda: a * b)

    def div(self, a, b):
        if not b:
            raise ZeroDivisionError('division by zero')
        p, q = self.bits(a), self.bits(b)
        if abs(b) == 1:
            return self._calculate(p, 1, lambda: a // b)
        return self._calculate(p, p * q, lambda: a // b)

    @_compound(3)
    def gcd(self, a, b, *, multiplier=1):
        a, b = abs(a), abs(b)
        self.bits(a); self.bits(b)
        while b:
            p, q = self.bits(a), self.bits(b)
            remainder = self._calculate(q, multiplier * max(1, p * q), lambda: a % b)
            a, b = b, remainder
        return a

    @_compound(3)
    def lcm(self, a, b):
        if not a or not b:
            self.charge(1); return 0
        return abs(self.mul(self.div(a, self.gcd(a, b)), b))

    @_compound(4)
    def fraction(self, numerator, denominator=1):
        if denominator == 0:
            raise InputError('Rational denominator is zero', stage=self.stage)
        p, q = self.bits(numerator), self.bits(denominator)
        # One reference Euclidean pass reserves both itself and Fraction's normalization.
        divisor = self.gcd(numerator, denominator, multiplier=2)
        g = max(1, divisor.bit_length())
        self.charge(max(1, p * g) + max(1, q * g))
        owner = ('fraction', self._serial); self._serial += 1
        self.ledger.acquire(owner, 128 + int_bytes(p) + int_bytes(q))
        try:
            return Fraction(numerator, denominator)
        finally:
            self.ledger.release(owner)

    @_compound(8)
    def qadd(self, a, b):
        g = self.gcd(a.denominator, b.denominator)
        left = self.div(b.denominator, g); right = self.div(a.denominator, g)
        numerator = self.add(self.mul(a.numerator, left), self.mul(b.numerator, right))
        return self.fraction(numerator, self.mul(a.denominator, left))

    @_compound(12)
    def qmul(self, a, b):
        g1 = self.gcd(a.numerator, b.denominator); g2 = self.gcd(b.numerator, a.denominator)
        return self.fraction(self.mul(self.div(a.numerator, g1), self.div(b.numerator, g2)),
                             self.mul(self.div(a.denominator, g2), self.div(b.denominator, g1)))

    @_compound(4)
    def qdiv(self, a, b):
        if b == 0:
            raise ZeroDivisionError('rational division by zero')
        inverse = self.fraction(b.denominator, b.numerator)
        return self.qmul(a, inverse)

    @_compound(2)
    def qle(self, a, b):
        return self.mul(a.numerator, b.denominator) <= self.mul(b.numerator, a.denominator)
