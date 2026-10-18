"""
Root execution orchestrator for 'Buy or Wait?' financial affordability agent system.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Add code/ to sys.path
code_dir = Path(__file__).resolve().parent / "code"
if str(code_dir) not in sys.path:
    sys.path.insert(0, str(code_dir))

from main import run_pipeline

if __name__ == "__main__":
    run_pipeline()
