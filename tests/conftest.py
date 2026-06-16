"""Shared test configuration.

Put the deployed indexer scripts (ansible/files) on sys.path so tests can import
kb_releases / kb_indexer the same flat way they are imported at runtime
({kb_home}/scripts).
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "ansible" / "files"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
