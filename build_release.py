"""Build a clean source distribution; never copy the user's databases or configuration."""
from pathlib import Path
import ast
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parent
EXCLUDE={'.venv','.backups','.ecosystem','__pycache__','logs','data','dist','reports','.git'}
SUFFIXES={'.py','.js','.cjs','.css','.html','.svg','.md','.bat','.ps1','.txt','.json','.png'}


def build():
    output=ROOT/'dist';output.mkdir(exist_ok=True)
    target=output/'LOCAL-WORK-AND-SETTING-Ecosystem-v2.1.0.zip'
    # Evaluate only the literal default settings; do not import app code or read personal settings.
    tree=ast.parse((ROOT/'local-ai-control-center/backend/config.py').read_text(encoding='utf-8'))
    config=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.AnnAssign) and getattr(node.target,'id','')=='DEFAULT_CONFIG')
    config['models']['scan_paths']=[]
    files=[]
    for p in sorted(ROOT.rglob('*')):
        rel=p.relative_to(ROOT)
        if any(part in EXCLUDE for part in rel.parts) or not p.is_file() or p.suffix not in SUFFIXES:continue
        if rel.as_posix()=='local-ai-control-center/config/app.json':continue
        files.append((p,rel))
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for p,rel in files:archive.write(p,'LOCAL WORK & SETTING/'+rel.as_posix())
        archive.writestr('LOCAL WORK & SETTING/local-ai-control-center/config/app.json',json.dumps(config,indent=2))
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            assert not any(part in EXCLUDE for part in Path(name).parts),name
            assert not name.endswith(('.db','-wal','-shm','.pyc','.exe')),name
        bundled=json.loads(archive.read('LOCAL WORK & SETTING/local-ai-control-center/config/app.json'))
        assert bundled['runtime']['model_path']=='' and bundled['models']['scan_paths']==[]
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print(f'PASS clean ZIP: {len(files)+1} files, {target.stat().st_size} bytes')
    print(target)
    return target


if __name__=='__main__':build()
