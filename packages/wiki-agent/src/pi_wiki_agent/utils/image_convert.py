"""Image-to-PNG conversion utility."""

from __future__ import annotations


def convert_to_png(data: bytes, source_format: str = "auto") -> bytes | None:
    """Convert image bytes to PNG format. Requires Pillow."""
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data))
        out = BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except ImportError:
        return None
    except Exception:
        return None
