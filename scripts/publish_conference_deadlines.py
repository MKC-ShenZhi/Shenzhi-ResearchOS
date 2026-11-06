#!/usr/bin/env python3
"""Compatibility entrypoint; run with the backend uv environment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/backend'))
from app.services.conferences.cli import main
if __name__ == '__main__':
    sys.argv.insert(1, 'publish')
    main()
