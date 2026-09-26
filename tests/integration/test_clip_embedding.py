from pathlib import Path

import pytest

from backend.core.config import settings
from backend.engines.embeddings.clip import image_embedding
from tests.preflight import ml_skip_reason


# BE-023 §8: distinguish ML UNAVAILABLE from a passing run. An anonymous
# `pytest.importorskip("torch")` hides the fact that nothing was verified;
# ml_skip_reason() names the exact state in the skip report instead.
_ML_REASON = ml_skip_reason()
if _ML_REASON:
    pytest.skip(_ML_REASON, allow_module_level=True)


TEST_IMAGE = Path(__file__).parents[2] / "test-image.jpg"


@pytest.mark.skipif(not TEST_IMAGE.exists(), reason="test-image.jpg is not present")
def test_clip_embedding_is_real_projected_vector():
    vector = image_embedding(TEST_IMAGE.read_bytes())

    assert isinstance(vector, list)
    assert len(vector) == settings.embedding_dimension == 512
    assert all(isinstance(value, float) for value in vector)
    assert any(value != 0.0 for value in vector)