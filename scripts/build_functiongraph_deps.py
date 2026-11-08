"""Build a separate FunctionGraph dependency ZIP on matching Linux / Python 3.9."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


def build(root, output, version='dev'):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', version):
        raise ValueError('Invalid version label')
    if platform.system() != 'Linux' or sys.version_info[:2] != (3, 9):
        raise RuntimeError('Run with Python 3.9 on Linux matching the function runtime, not macOS/Windows')
    architecture = platform.machine()
    if architecture not in ('x86_64', 'aarch64'):
        raise RuntimeError('Unsupported CPU architecture: ' + architecture)
    requirements = Path(root) / 'requirements.txt'
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    package = output / f'longfor-sign-functiongraph-deps-python3.9-{architecture}-{version}.zip'
    with tempfile.TemporaryDirectory(prefix='.functiongraph-deps-', dir=output) as directory:
        target = Path(directory) / 'packages'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                        '--no-cache-dir', '--only-binary=:all:', '--no-compile',
                        '--target', str(target), '-r', str(requirements)], check=True)
        # -S prevents an existing container/site-packages installation hiding missing ZIP files.
        verify = """import sys
sys.path.insert(0, sys.argv[1])
import cv2, numpy, requests
from PIL import Image
image = numpy.zeros((8, 8, 3), dtype=numpy.uint8)
assert cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).shape == (8, 8)
assert Image.fromarray(image).size == (8, 8)
print('Verified OpenCV', cv2.__version__, 'NumPy', numpy.__version__)
"""
        subprocess.run([sys.executable, '-S', '-c', verify, str(target)],
                       cwd=directory, env={**os.environ, 'PYTHONPATH': ''}, check=True)
        metadata = {'python': platform.python_version(), 'architecture': architecture,
                    'libc': platform.libc_ver(),
                    'requirements_sha256': hashlib.sha256(requirements.read_bytes()).hexdigest()}
        (target / 'FUNCTIONGRAPH_DEPENDENCIES.json').write_text(
            json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        # Packages and their bundled .libs directories belong directly at the ZIP root.
        pending = Path(directory) / 'dependencies.zip'
        with ZipFile(pending, 'w', ZIP_DEFLATED) as archive:
            for path in sorted(target.rglob('*')):
                if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                    continue
                info = ZipInfo(path.relative_to(target).as_posix())
                info.external_attr = (0o100755 if os.access(path, os.X_OK) else 0o100644) << 16
                info.compress_type = ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        with ZipFile(pending) as archive:
            if archive.testzip() is not None:
                raise RuntimeError('Dependency ZIP verification failed')
            unpacked = Path(directory) / 'unpacked'
            archive.extractall(unpacked)
        subprocess.run([sys.executable, '-S', '-c', verify, str(unpacked)],
                       cwd=directory, env={**os.environ, 'PYTHONPATH': ''}, check=True)
        os.replace(pending, package)
    checksum = hashlib.sha256(package.read_bytes()).hexdigest()
    package.with_suffix('.zip.sha256').write_text(f'{checksum}  {package.name}\n', encoding='ascii')
    return package


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='dev')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    print(build(root, args.output or root / 'dist/functiongraph', args.version))
