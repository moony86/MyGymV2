from types import SimpleNamespace
from pathlib import Path
import hashlib,json
import pytest
from src.services.exercise_media import for_exercise,LIBRARY


def test_every_asset_exists_with_reviewed_credit_and_matching_hash():
    root=LIBRARY.parent.parent
    for item in json.loads(LIBRARY.read_text(encoding='utf-8')):
        for asset in item['images']+([item['video']] if item.get('video') else []):
            assert asset['author'] and asset['license_url'].startswith('https://creativecommons.org/')
            assert asset['local_url'].startswith('/static/')
            path=root/asset['local_url'].lstrip('/')
            assert path.resolve().is_relative_to(root.resolve())
            assert hashlib.sha256(path.read_bytes()).hexdigest()==asset['sha256']


@pytest.mark.parametrize('name,equipment',[('Skull Crusher','barbell'),('Rear Delt Fly','machine'),('Preacher Curl (Machine)','machine'),('Leg Press Row','plate-loaded'),('Lateral Raise','cable')])
def test_misleading_variant_or_similar_name_never_selects_wrong_media(name,equipment):
    # Imported catalog variant IDs can be incorrect. Explicit name AND device must match.
    video,images=for_exercise(SimpleNamespace(name=name,equipment=equipment,knowledge_variant_id='variant.dumbbell_lateral_raise'))
    assert video is None and images==[]


def test_lying_and_generic_leg_curl_are_not_silently_equated():
    video,images=for_exercise(SimpleNamespace(name='Lying Leg Curl',equipment='machine'))
    assert video and len(images)==2
    assert for_exercise(SimpleNamespace(name='Leg Curl',equipment='machine'))==(None,[])
