import importlib
import importlib.util
import io
import unittest
from fractions import Fraction


class InputTests(unittest.TestCase):
    def module(self, name):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.' + name), 'Required module is not implemented')
        return importlib.import_module('dyadbridge.' + name)

    def model_data(self):
        return {'schema': 'dyadbridge.model.v1', 'states': ['B', 'A'],
                'rates': [{'from': 'A', 'to': 'B', 'rate': '2/4'}]}

    def test_exact_rationals(self):
        r = self.module('rational')
        for value, expected in [('2/4', Fraction(1, 2)), ('0.125', Fraction(1, 8)),
                                ('-0', Fraction(0)), (3, Fraction(3)), ('-2/3', Fraction(-2, 3))]:
            self.assertEqual(r.parse_rational(value), expected)
        self.assertEqual(r.format_rational(Fraction(-4, 2)), '-2')

    def test_invalid_rationals(self):
        r = self.module('rational'); errors = self.module('errors')
        for value in [True, 0.5, None, '1e-3', ' 1', '+1', '.5', '01', '1/0', 'NaN', 'Infinity', '1.2/3', '', '9' * 257, 2 ** 512]:
            with self.subTest(value=repr(value)[:50]), self.assertRaises(errors.InputError):
                r.parse_rational(value)

    def test_canonical_model(self):
        m = self.module('model'); model = m.Model.from_dict(self.model_data())
        self.assertEqual(model.states, ('A', 'B'))
        self.assertEqual(model.edges[0].rate, Fraction(1, 2))
        data = self.model_data(); data['states'].reverse(); data['rates'][0]['rate'] = '0.500'
        data['rates'].append({'from': 'B', 'to': 'A', 'rate': 0})
        self.assertEqual(model, m.Model.from_dict(data))
        self.assertEqual(model.to_dict()['rates'][0]['rate'], '1/2')

    def test_bad_model_shapes(self):
        m = self.module('model'); e = self.module('errors')
        bad = [dict(self.model_data(), extra=1), dict(self.model_data(), states=[]),
               dict(self.model_data(), states=['A', 'A']), dict(self.model_data(), states=['1A', 'B']),
               dict(self.model_data(), states=['A', '=B']), dict(self.model_data(), states=['A', 'é'])]
        for edge in [{'from': 'A', 'to': 'A', 'rate': 0}, {'from': 'A', 'to': 'Z', 'rate': 1},
                     {'from': 'A', 'to': 'B', 'rate': -1}, {'from': 'A', 'to': 'B', 'rate': 1, 'x': 0}]:
            bad.append(dict(self.model_data(), rates=[edge]))
        bad.append(dict(self.model_data(), rates=self.model_data()['rates'] * 2))
        for data in bad:
            with self.subTest(data=data), self.assertRaises(e.InputError): m.Model.from_dict(data)

    def test_state_boundary(self):
        m = self.module('model'); e = self.module('errors')
        for n in [1, 64]:
            self.assertEqual(len(m.Model.from_dict({'schema':'dyadbridge.model.v1', 'states':['S%d'%i for i in range(n)],'rates':[]}).states), n)
        with self.assertRaises(e.InputError):
            m.Model.from_dict({'schema':'dyadbridge.model.v1','states':['S%d'%i for i in range(65)],'rates':[]})

    def test_request(self):
        m = self.module('model'); e = self.module('errors'); model = m.Model.from_dict(self.model_data())
        raw = {'start':'A','end':'B','t0':0,'t1':'1/5'}
        request = m.BridgeRequest.from_dict(raw, model)
        self.assertEqual(request.epsilon, Fraction(1, 10**12)); self.assertEqual(request.time_bits, 32)
        for patch in [{'t1':-1}, {'start':'Z'}, {'epsilon':0}, {'epsilon':1}, {'time_bits':True}, {'time_bits':0}, {'time_bits':65}, {'seed':1}]:
            with self.subTest(patch=patch), self.assertRaises(e.InputError): m.BridgeRequest.from_dict(dict(raw, **patch), model)
        self.assertEqual(m.BridgeRequest.from_dict(dict(raw,t1=0), model).t1, 0)

    def test_run_options(self):
        m = self.module('model'); e = self.module('errors')
        self.assertEqual(m.RunOptions.from_dict({'seed':0}).samples, 1)
        for raw in [{}, {'seed':True}, {'seed':-1}, {'seed':2**64}, {'seed':0,'samples':0}, {'seed':0,'samples':True}, {'seed':0,'samples':10001}]:
            with self.subTest(raw=raw), self.assertRaises(e.InputError): m.RunOptions.from_dict(raw)

    def test_bounded_json(self):
        m = self.module('model'); e = self.module('errors')
        good = b'{"schema":"dyadbridge.model.v1","states":["A"],"rates":[]}'
        self.assertEqual(m.load_model(io.BytesIO(good)).states, ('A',))
        for raw in [good.replace(b'"rates":[]', b'"rates":[],"rates":[]'), b'\xff', b'['*17+b'0'+b']'*17, b' '*1048577, b'NaN', b'\xef\xbb\xbf'+good]:
            with self.subTest(size=len(raw)), self.assertRaises(e.InputError): m.load_model(io.BytesIO(raw))
        self.assertEqual(m.parse_json_bounded(io.BytesIO(b'"[\\\"]"')), '["]')

    def test_direct_value_objects_cannot_bypass_exact_contract(self):
        m = self.module('model'); e = self.module('errors')
        for make in [lambda: m.Model(('A','B'), (m.Edge(0,1,0.5),)),
                     lambda: m.Model(('B','A'), ()),
                     lambda: m.Model(('A','B'), (m.Edge(0,0,Fraction(1)),)),
                     lambda: m.BridgeRequest('A','B',0.0,Fraction(1)),
                     lambda: m.BridgeRequest('A','B',Fraction(1),Fraction(0))]:
            with self.assertRaises(e.InputError): make()

    def test_immutable_model(self):
        m = self.module('model'); model = m.Model.from_dict(self.model_data())
        with self.assertRaises(AttributeError): model.states = ('Z',)


if __name__ == '__main__': unittest.main()
