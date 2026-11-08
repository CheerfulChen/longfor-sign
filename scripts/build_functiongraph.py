"""Build independent fixed/random FunctionGraph bundles without personal config."""
import argparse
import hashlib
import re
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def write_zip(path, items):
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for name, data in sorted(items.items()):
            info = ZipInfo(name)
            info.external_attr = 0o100644 << 16
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    with ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('ZIP verification failed')


def build(root, output, version='dev'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', version):
        raise ValueError('Invalid version label')
    output = Path(output);output.mkdir(parents=True, exist_ok=True)
    products=[]
    for mode in ('fixed','random'):
        source = Path(root)/'cloud_function'/mode
        files = {p.name:p.read_bytes() for p in source.glob('*.py')}
        if 'main.py' not in files:raise ValueError('Missing function entry')
        for shared in ('longfor.py','bark_notify.py','requirements.txt'):
            files[shared]=(Path(root)/shared).read_bytes()
        for module in (Path(root)/'core').rglob('*.py'):
            files[module.relative_to(root).as_posix()]=module.read_bytes()
        code = output/f'longfor-sign-functiongraph-{mode}-code-{version}.zip'
        write_zip(code, files)
        template = (source/'functiongraph.yml').read_bytes()
        if b'CodeFileName: main.zip' not in template:raise ValueError('Template/source mismatch')
        bundle = output/f'longfor-sign-functiongraph-{mode}-{version}.zip'
        write_zip(bundle, {'functiongraph.yml':template,'main.zip':code.read_bytes()})
        products.extend((bundle,code))
    (output/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in products))
    return products


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default='dev')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    for product in build(root,args.output or root/'dist/functiongraph',args.version):print(product)
