"""Command line generation with complete-file, explicit-failure semantics."""
import argparse
from dataclasses import fields
import os
from pathlib import Path
import sys
import tempfile
import traceback
from .budget import Limits,WorkBudget
from .errors import DyadbridgeError,InputError
from .model import load_model,BridgeRequest,RunOptions
from .prepare import prepare
from .sample import sample_batch
from . import schema


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise InputError(message,stage='cli')


def _parser():
    parser=_Parser(prog='dyadbridge',description='Generate certified-truncation, quantized finite Markov bridge events.')
    parser.add_argument('--debug',action='store_true')
    commands=parser.add_subparsers(dest='command',required=True,parser_class=_Parser)
    for name in ('validate','prepare','sample'):
        command=commands.add_parser(name)
        command.add_argument('model',help='Model JSON file, or - for binary stdin')
        if name=='validate':continue
        command.add_argument('--start',required=True);command.add_argument('--end',required=True)
        command.add_argument('--t0',default='0');command.add_argument('--t1',required=True)
        command.add_argument('--epsilon',default='1/1000000000000')
        command.add_argument('--time-bits',type=int,default=32)
        for field in fields(Limits):command.add_argument('--'+field.name.replace('_','-'),type=int)
        if name=='sample':
            command.add_argument('--samples',type=int,default=1);command.add_argument('--seed',type=int,required=True)
            command.add_argument('--format',choices=('jsonl','csv'),default='jsonl')
            command.add_argument('--output');command.add_argument('--overwrite',action='store_true')
    return parser


def _write_records(stream,records):
    for record in records:stream.write(record)
    stream.flush()


def _io_error(exc,stdout,stderr,debug=False):
    if isinstance(exc,BrokenPipeError) and stdout is sys.stdout:
        # Prevent CPython's shutdown flush from retrying the broken pipe and
        # replacing the intended exit status with120. No model retry occurs.
        try:
            descriptor=os.open(os.devnull,os.O_WRONLY)
            try:os.dup2(descriptor,stdout.fileno())
            finally:os.close(descriptor)
        except (OSError,ValueError):pass
    stderr.write(schema.canonical({'code':'io-error','stage':'io','message':str(exc)})+'\n')
    if debug:traceback.print_exc(file=stderr)
    return 5


def main(argv=None,*,stdin=None,stdout=None,stderr=None):
    stdin=stdin if stdin is not None else sys.stdin.buffer
    stdout=stdout if stdout is not None else sys.stdout
    stderr=stderr if stderr is not None else sys.stderr
    temporary=None;debug=False
    try:
        args=_parser().parse_args(argv);debug=args.debug
        if args.model=='-':model=load_model(stdin)
        else:
            with open(args.model,'rb') as source:model=load_model(source)
        if args.command=='validate':
            stdout.write(schema.canonical({'schema':'dyadbridge.validation.v1','model_hash':schema.identity(model.to_dict()),
                                            'states':len(model.states),'edges':len(model.edges)})+'\n')
            stdout.flush()
            return 0
        request=BridgeRequest.from_dict({key:getattr(args,key) for key in ('start','end','t0','t1','epsilon','time_bits')},model)
        limits=Limits(**{field.name:getattr(args,field.name) for field in fields(Limits) if getattr(args,field.name) is not None})
        prepared=prepare(model,request,limits=limits)
        if args.command=='prepare':
            header=schema.run_record(prepared,1,0,prepared.certificate.tv_upper,budget=WorkBudget(limits,stage='report-preflight'))
            stdout.write(schema.canonical({'schema':'dyadbridge.preparation.v1','model_hash':header['model_hash'],
                                            'request_hash':header['request_hash'],'certificate':header['certificate'],
                                            'preparation':header['preparation']})+'\n')
            stdout.flush()
            return 0
        options=RunOptions.from_dict({key:getattr(args,key) for key in ('samples','seed','format','output','overwrite')})
        target=Path(options.output) if options.output and options.output!='-' else None
        if target is not None:
            exists=target.exists() or target.is_symlink()
            if exists and not options.overwrite:raise FileExistsError('Output exists; --overwrite is required')
            if target.is_dir():raise IsADirectoryError('Output target is a directory')
            if exists and not (target.is_file() or target.is_symlink()):raise OSError('Output target must be a regular file')
            handle=tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',newline='',dir=target.parent,
                                                prefix='.'+target.name+'.',suffix='.tmp',delete=False)
            temporary=Path(handle.name)
        else:handle=None
        try:
            batch=sample_batch(prepared,samples=options.samples,seed=options.seed)
            records=batch.to_jsonl() if options.format=='jsonl' else batch.to_csv()
            if handle is not None:
                with handle:_write_records(handle,records)
                if options.overwrite:os.replace(temporary,target)
                else:
                    # Link is atomic and refuses a target created during sampling.
                    os.link(temporary,target);temporary.unlink()
                temporary=None
            else:_write_records(stdout,records)
        finally:
            if handle is not None and not handle.closed:handle.close()
        return 0
    except DyadbridgeError as exc:
        stderr.write(schema.canonical(exc.to_dict())+'\n')
        if debug:traceback.print_exc(file=stderr)
        return exc.exit_code
    except OSError as exc:
        return _io_error(exc,stdout,stderr,debug)
    except SystemExit as exc:
        if exc.code==0:
            try:stdout.flush()
            except OSError as error:return _io_error(error,stdout,stderr,debug)
            return 0
        raise
    except Exception as exc:
        stderr.write(schema.canonical({'code':'internal-error','stage':'runtime','message':str(exc)})+'\n')
        if debug:traceback.print_exc(file=stderr)
        return 6
    finally:
        if temporary is not None:
            try:temporary.unlink(missing_ok=True)
            except OSError:pass


if __name__=='__main__':raise SystemExit(main())
