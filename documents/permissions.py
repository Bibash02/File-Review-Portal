from django.conf import settings
from rest_framework.exceptions import NotFound, PermissionDenied

from .models import Document, DocumentAccess, DocumentVersion, Level

OWNER = 50
ADMIN = 100
LEVEL_NAMES = {ADMIN: "admin", OWNER: "owner", Level.REVIEW: "review", Level.COMMENT: "comment", Level.VIEW: "view"}


def access_level(user, document) -> int:
    if user.is_superuser:
        return ADMIN
    if document.owner_id == user.id:
        return OWNER
    grant = DocumentAccess.objects.filter(document=document, user=user).values_list("level", flat=True).first()
    return grant or 0


def load_document(user, document_id, min_level=Level.VIEW):
    """404 if the user has no access at all (don't leak existence), 403 if access is too low."""
    doc = Document.objects.filter(pk=document_id, deleted_at__isnull=True).select_related("owner").first()
    level = access_level(user, doc) if doc else 0
    if level == 0:
        raise NotFound()
    if level < min_level:
        raise PermissionDenied("You don't have permission to do that on this document.")
    return doc, level


def visible_versions(document, level):
    """Reviewers/owner see every version; view/comment grantees only see the approved one."""
    qs = document.versions.filter(deleted_at__isnull=True)
    if level >= Level.REVIEW:
        return qs
    return qs.filter(pk=document.approved_version_id)


def load_version(document, level, version_id):
    version = visible_versions(document, level).filter(pk=version_id).first()
    if not version:
        raise NotFound()
    return version


def scan_allows_release(version) -> bool:
    S = DocumentVersion.ScanStatus
    if version.scan_status == S.INFECTED:
        return False
    if settings.REQUIRE_CLEAN_SCAN:
        return version.scan_status == S.CLEAN
    return True


def can_download(user, version) -> bool:
    document = version.document
    if version.deleted_at or document.deleted_at:
        return False
    level = access_level(user, document)
    if level == 0 or not scan_allows_release(version):
        return False
    if level >= Level.REVIEW:
        return True
    return version.pk == document.approved_version_id
