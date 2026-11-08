"""Private atomic state files for a single local/script process."""
import json
import os
import re
import tempfile
from pathlib import Path


class FileStore:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)

    def _path(self,key):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',key):raise ValueError('Invalid state key')
        return self.directory/(key+'.json')

    def load(self,key):
        try:return json.loads(self._path(key).read_text())
        except FileNotFoundError:return None

    def save(self,key,value):
        path=self._path(key)
        fd,temporary=tempfile.mkstemp(dir=self.directory,prefix='.state-')
        try:
            with os.fdopen(fd,'w') as output:
                json.dump(value,output,ensure_ascii=False);output.flush();os.fsync(output.fileno())
            os.replace(temporary,path)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
