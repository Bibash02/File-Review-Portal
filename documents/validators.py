import os
import zipfile

from django.conf import settings
from django.core.exceptions import ValidationError

# Magic bytes per extension. Extension alone is trivially spoofed.
SIGNATURES = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".docx": (b"PK\x03\x04",),
    ".txt": (),
}


def validate_upload(f):
    """Size + extension allowlist + content sniffing. Never trust the client Content-Type."""
    ext = os.path.splitext(f.name)[1].lower()

    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(sorted(settings.ALLOWED_UPLOAD_EXTENSIONS))
        raise ValidationError(f"File type '{ext or 'none'}' is not allowed. Allowed: {allowed}.")

    if f.size == 0:
        raise ValidationError("File is empty.")
    if f.size > settings.UPLOAD_MAX_BYTES:
        mb = settings.UPLOAD_MAX_BYTES / (1024 * 1024)
        raise ValidationError(f"File too large. Max size is {mb:g} MB.")

    f.seek(0)
    head = f.read(16)
    f.seek(0)

    signatures = SIGNATURES.get(ext, ())
    if signatures and not any(head.startswith(s) for s in signatures):
        raise ValidationError("File content does not match its extension.")

    if ext == ".txt":
        sample = f.read(8192)
        f.seek(0)
        if b"\x00" in sample:
            raise ValidationError("File content does not match its extension.")

    if ext == ".docx":
        try:
            ok = zipfile.is_zipfile(f) and "[Content_Types].xml" in zipfile.ZipFile(f).namelist()
        except zipfile.BadZipFile:
            ok = False
        f.seek(0)
        if not ok:
            raise ValidationError("File is not a valid .docx document.")
