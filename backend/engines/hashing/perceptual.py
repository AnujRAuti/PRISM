from io import BytesIO

import imagehash
from PIL import Image


def perceptual_hash(data: bytes) -> str:
    with Image.open(BytesIO(data)) as image:
        return str(imagehash.phash(image))