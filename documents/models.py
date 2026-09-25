import os
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from .storage import get_private_storage


class Level(models.IntegerChoices):
    """Per-document permission levels (owner/admin are implied, not stored)."""
    VIEW = 10, "View approved version"
    COMMENT = 20, "View approved version + read/write comments"
    REVIEW = 30, "Review: see all versions, comment, approve/reject"


def version_upload_path(instance, filename):
    # Storage name is OURS. The user's filename never touches the filesystem.
    ext = os.path.splitext(filename)[1].lower()
    return f"documents/{instance.document_id}/v{instance.version_number}/{uuid.uuid4().hex}{ext}"


class DocumentQuerySet(models.QuerySet):
    def visible_to(self, user):
        qs = self.filter(deleted_at__isnull=True)
        if user.is_superuser:
            return qs
        return qs.filter(Q(owner=user) | Q(access_grants__user=user)).distinct()


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    # Latest APPROVED version. Old approved version stays live until a newer one is approved.
    approved_version = models.ForeignKey(
        "DocumentVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DocumentQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    class ScanStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEAN = "clean", "Clean"
        INFECTED = "infected", "Infected"
        SKIPPED = "skipped", "Skipped (no scanner)"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()

    file = models.FileField(upload_to=version_upload_path, storage=get_private_storage, max_length=255)
    original_name = models.CharField(max_length=255)   # sanitized, display/download name only
    content_type = models.CharField(max_length=100)    # derived server-side from extension
    size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)

    scan_status = models.CharField(max_length=10, choices=ScanStatus.choices, default=ScanStatus.PENDING)
    review_status = models.CharField(max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete; cleanup job purges

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["document", "version_number"], name="uniq_document_version_number")
        ]

    def __str__(self):
        return f"{self.document_id} v{self.version_number}"


class Comment(models.Model):
    version = models.ForeignKey(DocumentVersion, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class DocumentAccess(models.Model):
    """Per-file permission grant."""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="access_grants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="document_grants")
    level = models.PositiveSmallIntegerField(choices=Level.choices)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["document", "user"], name="uniq_document_user_grant")]
