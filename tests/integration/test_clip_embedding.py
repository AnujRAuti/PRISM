from pathlib import Path

import pytest

from backend.core.config import settings
from backend.engines.embeddings.clip import image_embedding


pytest.importorskip("torch")
pytest.importorskip("transformers")


TEST_IMAGE = Path(__file__).parents[2] / "test-image.jpg"


@pytest.mark.skipif(not TEST_IMAGE.exists(), reason="test-image.jpg is not present")
def test_clip_embedding_is_real_projected_vector():
    vector = image_embedding(TEST_IMAGE.read_bytes())

    assert isinstance(vector, list)
    assert len(vector) == settings.embedding_dimension == 512
    assert all(isinstance(value, float) for value in vector)
    assert any(value != 0.0 for value in vector)