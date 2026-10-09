"""Stable, explicit failure classes. No sampler retries these failures."""


class DyadbridgeError(Exception):
    exit_code = 6
    code = 'internal-error'

    def __init__(self, message, *, stage='validation', **context):
        super().__init__(message)
        self.stage = stage
        self.context = context

    def to_dict(self):
        from fractions import Fraction
        from .rational import format_rational
        context = {key:format_rational(value) if isinstance(value,Fraction) else value
                   for key,value in self.context.items()}
        return {'code': self.code, 'stage': self.stage, 'message': str(self), **context}


class InputError(DyadbridgeError):
    exit_code = 2
    code = 'invalid-input'


class ImpossibleEndpoint(DyadbridgeError):
    exit_code = 3
    code = 'impossible-endpoint'


class ResourceLimitError(DyadbridgeError):
    exit_code = 4
    code = 'resource-limit'


class UnsupportedRuntime(ResourceLimitError):
    code = 'unsupported-runtime'


class RandomSourceError(DyadbridgeError):
    code = 'invalid-bit-source'


class InvariantError(DyadbridgeError):
    code = 'internal-invariant'
