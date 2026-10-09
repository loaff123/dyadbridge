"""Exact integer categoricals under an ideal-bit model; seeded replay is separate."""
from bisect import bisect_right
from functools import lru_cache
import platform
import random as _stdlib_random
import sys
from .errors import RandomSourceError, UnsupportedRuntime
from .model import strict_integer

RNG_ID='cpython-mt19937-getrandbits-v1'
_VECTOR=(0,1,827307999,3255389356,3823568514,4776171008201404212,68895973194594625658978287685821052154)


@lru_cache(maxsize=1)
def check_runtime():
    if platform.python_implementation() != 'CPython' or not (3,11) <= sys.version_info[:2] < (3,15):
        raise UnsupportedRuntime('Seeded replay supports CPython 3.11–3.14 only',stage='runtime')
    source=_stdlib_random.Random(0)
    if tuple(source.getrandbits(k) for k in (0,1,31,32,33,64,127)) != _VECTOR:
        raise UnsupportedRuntime('Runtime random-bit compatibility vector differs',stage='runtime')
    return True


def seeded_source(seed):
    strict_integer(seed,0,2**64-1,'seed')
    check_runtime()
    return _stdlib_random.Random(seed)


def getbits(source,bits):
    value=source.getrandbits(bits)
    if type(value) is not int or value < 0 or value.bit_length() > bits:
        raise RandomSourceError('Bit source returned a noninteger or out-of-range value',stage='sampling')
    return value


def randbelow(total,source):
    if total == 1:return 0
    if type(total) is not int or total < 1:raise ValueError('Positive integer total required')
    bits=(total-1).bit_length()
    while True:
        ticket=getbits(source,bits)
        if ticket < total:return ticket


def choose(table,source):
    if len(table.outcomes)==1:return table.outcomes[0]
    return table.outcomes[bisect_right(table.cumulative,randbelow(table.total,source))]
