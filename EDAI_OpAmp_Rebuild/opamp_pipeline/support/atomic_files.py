"""Publish complete text files, retrying transient Windows reader/share locks."""
import os
import tempfile
import time
from pathlib import Path


def atomic_write_bytes(path, data, *, replace_attempts=8):
    if replace_attempts < 1:
        raise ValueError('At least one publish attempt is required')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A private staging file prevents another writer from replacing our payload.
    with tempfile.NamedTemporaryFile(mode='wb',
            prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent, delete=False) as stream:
        staging = Path(stream.name)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    for attempt in range(replace_attempts):
        try:
            os.replace(staging, path)
            return
        except OSError as error:
            transient = getattr(error, 'winerror', None) in {5, 32, 33}
            if not transient or attempt + 1 == replace_attempts:
                error.add_note('Unpublished staging file retained at ' + str(staging))
                raise
            time.sleep(min(.05 * 2 ** attempt, .4))


def atomic_write_text(path, text, *, replace_attempts=8):
    atomic_write_bytes(path, text.encode('utf-8'), replace_attempts=replace_attempts)
