"""Start the existing authenticated RiceGrade ML service on loopback.

Uses a token supplied interactively, never written to a file or Git.
Run this only during supervised development; the tunnel URL is public.
"""
from __future__ import annotations

import getpass
import os
import sys


def main() -> int:
    token = os.environ.get('RICEGRADE_ML_TOKEN')
    if not token:
        print('Paste the *same* RICEGRADE_ML_TOKEN configured as a Cloudflare Pages Production secret.')
        token = getpass.getpass('Private token (input hidden): ').strip()
    if len(token) < 32:
        print('Error: token must contain at least 32 characters.', file=sys.stderr)
        return 1
    os.environ['RICEGRADE_ML_TOKEN'] = token
    # Import the server only after setting secrets and before listening.
    try:
        import uvicorn
    except ImportError:
        print('Missing uvicorn. Install requirements-server.txt in your virtual environment.', file=sys.stderr)
        return 1
    uvicorn.run('server:app', host='127.0.0.1', port=8080, log_level='info', access_log=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
