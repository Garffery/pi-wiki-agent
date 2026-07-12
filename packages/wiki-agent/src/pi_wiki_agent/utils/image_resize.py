"""Image resize utility."""

from __future__ import annotations


def resize_image(data: bytes, max_width: int = 1024, max_height: int = 1024) -> bytes | None:
    """Resize image to fit within max dimensions, preserving aspect ratio. Requires Pillow."""
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data))
        img.thumbnail((max_width, max_height))
        out = BytesIO()
        img.save(out, format=img.format or "PNG")
        return out.getvalue()
    except ImportError:
        return None
    except Exception:
        return None
