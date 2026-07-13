import sys
from pathlib import Path

# أضف مجلد "src" إلى مسار البحث عن الموديولات
sys.path.insert(0, str(Path(__file__).parent / "src"))