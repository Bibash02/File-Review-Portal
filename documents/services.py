import hashlib
import os

from django.core.exceptions import SuspiciousFileOperation
from django.db import transaction
from django.db.models import Max
from django.utils.text import get_valid_filename

from .models import Document, DocumentVersion
from .scanning import scan_version

CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


def clean_filename(raw: str) -> str:
    """User filenames are input: strip paths, weird chars, cap length."""
    base = os.path.basename(raw.replace("\\", "/"))
    try:
        safe = get_valid_filename(base)
    except SuspiciousFileOperation:
        safe = "upload"
    stem, ext = os.path.splitext(safe)
    return f"{stem[:100] or 'upload'}{ext.lower()}"


@transaction.atomic
def create_version(document: Document, uploaded_file, user) -> DocumentVersion:
    # Lock the parent row so two concurrent uploads can't grab the same version number.
    Document.objects.select_for_update().get(pk=document.pk)
    last = document.versions.aggregate(m=Max("version_number"))["m"] or 0

    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    version = DocumentVersion(
        document=document,
        version_number=last + 1,
        original_name=clean_filename(uploaded_file.name),
        content_type=CONTENT_TYPES[ext],
        size=uploaded_file.size,
        sha256=digest.hexdigest(),
        uploaded_by=user,
    )
    version.file.save(uploaded_file.name, uploaded_file, save=False)
    version.save()
    scan_version(version)  # prod: transaction.on_commit(lambda: scan_task.delay(version.pk))
    return version
