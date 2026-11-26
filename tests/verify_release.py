"""Verify bundled bytecode matches the reviewed source, excluding path/line metadata."""
import hashlib
import marshal
import sys
import types
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader


def normalized(value):
    if isinstance(value,types.CodeType):
        return (value.co_code,value.co_names,value.co_varnames,value.co_freevars,value.co_cellvars,tuple(normalized(c) for c in value.co_consts),value.co_argcount,value.co_kwonlyargcount,value.co_flags)
    if isinstance(value,tuple):return tuple(normalized(v) for v in value)
    if isinstance(value,frozenset):return tuple(sorted(map(repr,value)))
    return value


def verify(root,release=None):
    root=Path(root);release=Path(release) if release else root/'dist/ThreadsStudioPro21';archive=CArchiveReader(str(release/'ThreadsStudioPro.exe'));pyz=archive.open_embedded_archive('PYZ.pyz')
    modules=['pro','app','threadstudio.source','threadstudio.render','threadstudio.store','threadstudio.production','threadstudio.tiktok','threadstudio.browser_publish','threadstudio.secrets','threadstudio.voice_api','threadstudio.voice_ui','threadstudio.editing','threadstudio.editing_ui']
    for name in modules:
        code=marshal.loads(archive.extract(name)) if name=='pro' else pyz.extract(name)
        source=root/(name.replace('.','/')+'.py');compiled=compile(source.read_text(encoding='utf8'),str(source),'exec',optimize=0)
        if normalized(code)!=normalized(compiled):raise AssertionError('Bundled source mismatch: '+name)
    print('PASS: all '+str(len(modules))+' bundled modules match final source.')


if __name__=='__main__':verify(Path(__file__).resolve().parent.parent,sys.argv[1] if len(sys.argv)>1 else None)
