"""Strict exact inputs and bounded decimal conversion, without global settings."""
import re
from contextlib import nullcontext
from fractions import Fraction
from .budget import WorkBudget
from .errors import InputError

RATIONAL = re.compile(r'-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*|\.[0-9]+)?\Z')


def decimal_integer(text, *, max_bits=32768, budget=None):
    negative = text.startswith('-')
    digits = text[1:] if negative else text
    if not digits or not digits.isascii() or not digits.isdigit():
        raise InputError('Invalid decimal integer')
    if len(digits) > (max_bits * 30103 + 99999) // 100000:
        raise InputError('Decimal integer exceeds bit ceiling')
    bound=min(max_bits,max(1,(len(digits)*3322+999)//1000))
    frame=budget.scratch(5,bound,256) if budget else nullcontext()
    with frame:
        value = 0
        for start in range(0, len(digits), 9):
            piece = digits[start:start + 9]
            multiplier = 10 ** len(piece)
            value = (budget.add(budget.mul(value, multiplier), int(piece)) if budget
                     else value * multiplier + int(piece))
            if value.bit_length() > max_bits:
                raise InputError('Decimal integer exceeds bit ceiling')
        return -value if negative else value


def decimal_string(value, *, budget=None):
    bits=max(1,abs(value).bit_length())
    chunks=(bits+28)//29
    frame=budget.scratch(3,bits,256+chunks*128+(bits*30103+99999)//100000) if budget else nullcontext()
    with frame:
        if value == 0:
            if budget:budget.charge(1)
            return '0'
        sign = '-' if value < 0 else ''
        value = abs(value)
        pieces = []
        while value:
            if budget:budget.charge(max(1,value.bit_length())*30)
            value, tail = divmod(value, 10**9)
            pieces.append(tail)
        return sign + str(pieces[-1]) + ''.join('%09d' % part for part in reversed(pieces[:-1]))


def format_rational(value, *, budget=None):
    numerator = decimal_string(value.numerator,budget=budget)
    return numerator if value.denominator == 1 else numerator + '/' + decimal_string(value.denominator,budget=budget)


def parse_rational(value, *, budget=None):
    budget = budget or WorkBudget(stage='ingestion')
    if type(value) is int:
        if abs(value).bit_length() > 512:
            raise InputError('Input numerator exceeds 512 bits')
        return budget.fraction(value)
    if type(value) is not str or len(value) > 256 or not RATIONAL.fullmatch(value):
        raise InputError('Expected an exact integer, decimal string or p/q string')
    if '/' in value:
        numerator, denominator = value.split('/')
        n = decimal_integer(numerator, max_bits=852, budget=budget)
        d = decimal_integer(denominator, max_bits=852, budget=budget)
    elif '.' in value:
        left, right = value.split('.')
        n = decimal_integer(left + right, max_bits=852, budget=budget)
        d = 1
        for _ in right:
            d = budget.mul(d, 10)
    else:
        n = decimal_integer(value, max_bits=852, budget=budget); d = 1
    result = budget.fraction(n, d)
    if max(abs(result.numerator).bit_length(), result.denominator.bit_length()) > 512:
        raise InputError('Reduced input rational parts exceed 512 bits')
    return result
