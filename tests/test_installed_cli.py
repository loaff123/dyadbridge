import json,os,subprocess,tempfile,tomllib,unittest
from pathlib import Path


class InstalledTests(unittest.TestCase):
    def test_spdx_license_has_compatible_build_backend_floor(self):
        root=Path(__file__).parents[1]
        metadata=tomllib.loads((root/'pyproject.toml').read_text())
        self.assertEqual(metadata['project']['license'],'MIT')
        self.assertEqual(metadata['build-system']['build-backend'],'setuptools.build_meta')
        # PEP 639 SPDX strings require setuptools 77+; exercise the chosen
        # 77.0.3 minimum in the separate isolated build-floor qualification.
        self.assertIn('setuptools>=77.0.3',metadata['build-system']['requires'])
        self.assertEqual(metadata['project']['dependencies'],[])

    def test_distribution_assets_are_present(self):
        root=Path(__file__).parents[1]
        self.assertTrue((root/'LICENSE').is_file(),'License is not packaged yet')
        self.assertTrue((root/'src/dyadbridge/data/hky.json').is_file(),'Installed example is not packaged yet')

    def test_clean_installed_api_and_cli(self):
        interpreters=json.loads(os.environ.get('DYADBRIDGE_INSTALLED_PYTHONS','[]'))
        if not interpreters:self.skipTest('Set DYADBRIDGE_INSTALLED_PYTHONS for separately provisioned clean installs')
        code='''import importlib.util,json,sys,subprocess
from pathlib import Path
import dyadbridge
from dyadbridge import Model,BridgeRequest,prepare,sample_batch,read_jsonl
import io
assert Path(dyadbridge.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
for dependency in ('numpy','scipy','mpmath'):assert importlib.util.find_spec(dependency) is None
model=Model.from_dict({'schema':'dyadbridge.model.v1','states':['A','B'],'rates':[{'from':'A','to':'B','rate':1}]})
request=BridgeRequest.from_dict({'start':'A','end':'B','t0':0,'t1':1},model)
batch=sample_batch(prepare(model,request),samples=3,seed=17)
assert len(read_jsonl(io.BytesIO(''.join(batch.to_jsonl()).encode())).histories)==3
r=subprocess.run([sys.executable,'-m','dyadbridge','validate','-'],input=json.dumps(model.to_dict()).encode(),capture_output=True)
assert r.returncode==0,r.stderr
assert json.loads(r.stdout)['states']==2
entry=Path(sys.executable).parent/'dyadbridge'
r=subprocess.run([str(entry),'--help'],capture_output=True)
assert r.returncode==0,r.stderr
from importlib import metadata,resources
assert not metadata.distribution('dyadbridge').requires
assert resources.files('dyadbridge').joinpath('data','hky.json').is_file()
print('clean installed API, JSONL readback, CLI and no scientific dependencies: passed')
'''
        env=dict(os.environ);env.pop('PYTHONPATH',None)
        for interpreter in interpreters:
            with self.subTest(interpreter=interpreter),tempfile.TemporaryDirectory() as directory:
                result=subprocess.run([interpreter,'-I','-c',code],cwd=directory,env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=='__main__':unittest.main()
