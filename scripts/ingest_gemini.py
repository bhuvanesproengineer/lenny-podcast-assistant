#!/usr/bin/env python
"""
Root-level entry point for Gemini transcript ingestion pipeline.
Delegates directly to backend/scripts/ingest_gemini.py.
"""
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
root_dir = Path(__file__).resolve().parent.parent
backend_dir = root_dir / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scripts.ingest_gemini import main

if __name__ == "__main__":
    main()
