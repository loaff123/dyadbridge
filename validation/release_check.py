"""Verify final source/archive identity and absence of private/build artifacts."""
import argparse,email,hashlib,json,re,tarfile,zipfile
from pathlib import Path


def digest(data):return hashlib.sha256(data).hexdigest()


def check(source,wheel,sdist):
    source=Path(source).resolve()
    with zipfile.ZipFile(wheel) as archive:
        wheel_files={name:archive.read(name) for name in archive.namelist() if not name.endswith('/')}
    with tarfile.open(sdist,'r:gz') as archive:
        members=[m for m in archive.getmembers() if m.isfile()]
        prefix=members[0].name.split('/')[0]+'/'
        sdist_files={m.name[len(prefix):]:archive.extractfile(m).read() for m in members}
    forbidden=('__pycache__','.git/','.pyc')
    for name,data in list(wheel_files.items())+list(sdist_files.items()):
        assert not name.startswith('/') and '..' not in Path(name).parts,name
        assert not any(part in name for part in forbidden),name
        assert re.search(rb'/(?:home|workspace|tmp)/[A-Za-z0-9_.-]+/',data) is None,('machine-specific path',name)
    metadata=email.message_from_bytes(next(value for name,value in wheel_files.items() if name.endswith('.dist-info/METADATA')))
    assert not metadata.get_all('Requires-Dist'),metadata.get_all('Requires-Dist')
    expected=[]
    for relative in ['LICENSE','MANIFEST.in','README.md','requirements-validation.txt','pyproject.toml']:
        expected.append(source/relative)
    for directory in ['src/dyadbridge','tests','validation','docs','examples']:
        expected.extend(path for path in (source/directory).rglob('*') if path.is_file() and path.suffix in ('.py','.md','.json','.jsonl','.csv','.txt') and '__pycache__' not in path.parts)
    checked=[]
    for path in sorted(set(expected)):
        relative=path.relative_to(source).as_posix();data=path.read_bytes()
        assert sdist_files.get(relative)==data,('sdist/source mismatch',relative)
        if relative.startswith('src/dyadbridge/'):
            name=relative[4:]
            assert wheel_files.get(name)==data,('wheel/source mismatch',relative)
        checked.append({'path':relative,'sha256':digest(data)})
    assert any(name.endswith('/licenses/LICENSE') for name in wheel_files)
    return {'status':'passed','source_files_checked':len(checked),'source_files':checked,
            'wheel_sha256':digest(Path(wheel).read_bytes()),'sdist_sha256':digest(Path(sdist).read_bytes()),
            'runtime_requires_dist':metadata.get_all('Requires-Dist') or []}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',default=str(Path(__file__).parents[1]))
    parser.add_argument('--wheel',required=True);parser.add_argument('--sdist',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=check(args.source,args.wheel,args.sdist)
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n');print('Verified',result['source_files_checked'],'source files, both archives and empty runtime dependencies')
