import importlib,importlib.util,io,json,os,subprocess,sys,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from test_prepare import problem


class CLITests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('dyadbridge.cli'),'CLI is not implemented')
        return importlib.import_module('dyadbridge.cli')

    def raw(self):return json.dumps(problem(['A','B'],[('A','B',1),('B','A',1)],'A','B')[0].to_dict()).encode()

    def call(self,args):
        c=self.module();out=io.StringIO();err=io.StringIO()
        code=c.main(args,stdin=io.BytesIO(self.raw()),stdout=out,stderr=err)
        return code,out.getvalue(),err.getvalue()

    def test_validate_prepare_and_sample(self):
        self.assertEqual(self.call(['validate','-'])[0],0)
        base=['-','--start','A','--end','B','--t1','1']
        code,text,error=self.call(['prepare']+base)
        self.assertEqual(code,0,error);self.assertIn('certificate',json.loads(text))
        for format_ in ['jsonl','csv']:
            code,text,error=self.call(['sample']+base+['--seed','17','--samples','3','--format',format_])
            self.assertEqual(code,0,error);self.assertIn('complete',text)

    def test_error_codes(self):
        cases=[(['sample','-','--start','A','--end','B','--t1','1'],2),
               (['prepare','-','--start','A','--end','B','--t1','0'],3),
               (['prepare','-','--start','A','--end','B','--t1','65'],4),
               (['prepare','-','--start','A','--end','B','--t1','1e-3'],2)]
        for args,expected in cases:
            code,text,error=self.call(args);self.assertEqual(code,expected,error);self.assertEqual(text,'');self.assertIn('code',json.loads(error))

    def test_preparation_report_conversion_is_bounded(self):
        value=str(2**511-1)
        code,text,error=self.call(['prepare','-','--start','A','--end','A','--t0',value,'--t1',value,
                                  '--epsilon','1/2','--time-bits','1','--max-work','5000'])
        self.assertEqual(code,4,error);self.assertEqual(text,'')

    def test_atomic_output_and_no_unapproved_overwrite(self):
        c=self.module()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl';path.write_text('original')
            args=['sample','-','--start','A','--end','B','--t1','1','--seed','17','--output',str(path)]
            with patch.object(c,'sample_batch',side_effect=AssertionError('RNG stage reached')):
                self.assertEqual(self.call(args)[0],5)
            self.assertEqual(path.read_text(),'original')
            with patch.object(c,'_write_records',side_effect=OSError('injected write failure')):
                self.assertEqual(self.call(args+['--overwrite'])[0],5)
            self.assertEqual(path.read_text(),'original');self.assertEqual(list(Path(directory).iterdir()),[path])
            self.assertEqual(self.call(args+['--overwrite'])[0],0)
            self.assertIn('complete',path.read_text())

    def test_existing_directory_is_refused_before_rng(self):
        c=self.module()
        with tempfile.TemporaryDirectory() as directory:
            args=['sample','-','--start','A','--end','B','--t1','1','--seed','17',
                  '--output',directory,'--overwrite']
            with patch.object(c,'sample_batch',side_effect=AssertionError('RNG stage reached')):
                code,text,error=self.call(args)
            self.assertEqual(code,5,error);self.assertEqual(text,'')

    def test_real_closed_stdout_pipe_exits_five(self):
        self.module()
        commands=[['validate','-'],['prepare','-','--start','A','--end','B','--t1','1'],
                  ['sample','-','--start','A','--end','B','--t1','1','--seed','17']]
        for command in commands:
            read_fd,write_fd=os.pipe();os.close(read_fd)
            try:
                result=subprocess.run([sys.executable,'-m','dyadbridge']+command,
                    input=self.raw(),stdout=write_fd,stderr=subprocess.PIPE)
            finally:os.close(write_fd)
            with self.subTest(command=command):
                self.assertEqual(result.returncode,5,result.stderr)
                self.assertEqual(json.loads(result.stderr)['code'],'io-error')

    def test_module_entry_point(self):
        self.module()
        result=subprocess.run([sys.executable,'-m','dyadbridge','validate','-'],input=self.raw(),capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['states'],2)

if __name__=='__main__':unittest.main()
