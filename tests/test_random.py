import importlib
import importlib.util
import unittest


class Tape:
    def __init__(self,values):self.values=iter(values);self.requests=[]
    def getrandbits(self,k):self.requests.append(k);return next(self.values)


class RandomTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.random'),'Random module is not implemented')
        return importlib.import_module('dyadbridge.random')

    def test_rejection_and_singleton(self):
        r=self.module();tape=Tape([7,4])
        self.assertEqual(r.randbelow(1,tape),0);self.assertEqual(tape.requests,[])
        self.assertEqual(r.randbelow(5,tape),4);self.assertEqual(tape.requests,[3,3])
        tape=Tape([7]*10001+[0]);self.assertEqual(r.randbelow(5,tape),0)
        self.assertEqual(len(tape.requests),10002)

    def test_exact_ticket_intervals(self):
        r=self.module()
        from dyadbridge.prepare import Categorical
        table=Categorical((8,9),(2,5))
        self.assertEqual([r.choose(table,Tape([n])) for n in range(5)],[8,8,9,9,9])
        self.assertEqual(r.choose(Categorical((8,),(999,)),Tape([])),8)

    def test_source_values(self):
        r=self.module()
        from dyadbridge.errors import RandomSourceError
        for invalid in [True,-1,8,0.5,None]:
            with self.subTest(value=invalid), self.assertRaises(RandomSourceError):r.getbits(Tape([invalid]),3)

    def test_seeded_stream(self):
        r=self.module();a=r.seeded_source(17);b=r.seeded_source(17)
        self.assertEqual([r.getbits(a,k) for k in [1,32,64,127]],[r.getbits(b,k) for k in [1,32,64,127]])
        self.assertTrue(r.check_runtime())

if __name__=='__main__':unittest.main()
