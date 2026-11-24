import os
from pathlib import Path


def analysis_dir():
    return Path(os.environ.get('ANALYSIS_DIR', '/analysis'))
