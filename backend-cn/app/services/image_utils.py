from io import BytesIO

from PIL import Image, ImageOps

from app.logger import get_logger

logger = get_logger("image_utils")


def resize_if_needed(image_bytes: bytes, max_dimension: int) -> bytes:
    img = Image.open(BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)

    width, height = img.size
    if width <= max_dimension and height <= max_dimension:
        return image_bytes

    img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    new_w, new_h = img.size

    buf = BytesIO()
    fmt = img.format or "PNG"
    if fmt == "JPEG":
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=95)
    elif fmt == "WEBP":
        img.save(buf, format="WEBP", quality=95)
    else:
        img.save(buf, format="PNG", optimize=True)

    logger.info("图片已缩放: %dx%d -> %dx%d", width, height, new_w, new_h)
    return buf.getvalue()
