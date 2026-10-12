"""Verify the frozen model artifacts without importing torch or performing training."""
import hashlib
import json
from pathlib import Path
import sys


def verify(bundle: Path) -> dict:
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    expected = manifest.get('files', {})
    if len(expected) != 6:
        raise ValueError('Expected six artifact checksums')
    checks = {}
    for filename, target_digest in expected.items():
        path = bundle / filename
        if not path.is_file() or path.name != filename:
            raise FileNotFoundError(filename)
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        checks[filename] = current == target_digest
    if not all(checks.values()):
        raise ValueError('Frozen bundle checksum mismatch: ' + ', '.join(k for k,v in checks.items() if not v))
    return checks


if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / 'models' / 'final_ricegrade'
    print('PASS: verified frozen model artifacts:', ', '.join(verify(target)))
