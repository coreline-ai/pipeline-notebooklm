"""테스트 공통 설정."""

import sys
from pathlib import Path

# src/ 를 import path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
