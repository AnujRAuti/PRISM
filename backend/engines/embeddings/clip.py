from io import BytesIO
from typing import Any

from backend.core.config import settings


_processor: Any | None = None
_model: Any | None = None


def image_embedding(data: bytes) -> list[float]:
    global _processor, _model
    try:
        import torch
        from PIL import Image
        from transformers import CLIPModel, CLIPProcessor
    except ImportError as error:
        raise RuntimeError(
            "Embedding runtime unavailable; install compatible torch and transformers packages"
        ) from error

    if _processor is None or _model is None:
        _processor = CLIPProcessor.from_pretrained(settings.embedding_model_name)
        _model = CLIPModel.from_pretrained(settings.embedding_model_name)
        _model.eval()
    image = Image.open(BytesIO(data)).convert("RGB")
    inputs = _processor(images=image, return_tensors="pt")
    with torch.no_grad():
        vector = _model.get_image_features(**inputs)[0]
        vector = vector / vector.norm(p=2)
    values = vector.cpu().tolist()
    if len(values) != settings.embedding_dimension:
        raise RuntimeError("Embedding dimension does not match configured schema")
    return values