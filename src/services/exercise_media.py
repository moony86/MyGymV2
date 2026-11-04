"""Only explicit, reviewed exercise-name AND apparatus bindings select media."""
import json
from pathlib import Path

LIBRARY = Path(__file__).resolve().parents[2] / 'static' / 'exercise-library.json'


def for_exercise(exercise):
    if not LIBRARY.exists():
        return None, []
    name = exercise.name.strip().casefold()
    equipment = (exercise.equipment or '').strip().casefold()
    for item in json.loads(LIBRARY.read_text(encoding='utf-8')):
        if any(binding['name'].strip().casefold() == name and binding['equipment'].casefold() == equipment
               for binding in item['bindings']):
            return item.get('video'), item.get('images', [])
    return None, []
