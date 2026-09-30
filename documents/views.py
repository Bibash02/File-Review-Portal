from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import APIException, NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Comment, Document, DocumentAccess, DocumentVersion, Level
from .permissions import (
    OWNER, access_level, can_download, load_document, load_version, scan_allows_release, visible_versions,
)
from .serializers import (
    AccessGrantSerializer, CommentSerializer, DocumentCreateSerializer, DocumentSerializer,
    ReviewSerializer, UploadSerializer, VersionSerializer,
)
from .services import create_version

User = get_user_model()
DOWNLOAD_SALT = "documents.download-link"


class PayloadTooLarge(APIException):
    status_code = 413
    default_detail = "Upload too large."
    default_code = "payload_too_large"


def reject_oversized(request):
    """Cheap early check on Content-Length before DRF parses the body.
    (Real limit belongs on the proxy too: nginx client_max_body_size.)"""
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > settings.UPLOAD_MAX_BYTES + 64 * 1024:
        raise PayloadTooLarge()


def file_response(version):
    try:
        fh = version.file.storage.open(version.file.name, "rb")
    except FileNotFoundError:
        raise Http404("File missing from storage.")
    resp = FileResponse(fh, as_attachment=True, filename=version.original_name)
    resp["Content-Type"] = version.content_type
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, no-store"
    return resp


# ---------------------------------------------------------------- documents
class DocumentViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        return Document.objects.visible_to(self.request.user).select_related("owner", "approved_version")

    def get_throttles(self):
        self.throttle_scope = "uploads" if self.action == "create" else None
        return super().get_throttles()

    def create(self, request):
        reject_oversized(request)
        s = DocumentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            doc = Document.objects.create(owner=request.user, title=s.validated_data["title"])
            create_version(doc, s.validated_data["file"], request.user)
        return Response(DocumentSerializer(doc, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if access_level(self.request.user, instance) < OWNER:
            raise PermissionDenied("Only the owner can delete a document.")
        now = timezone.now()  # soft delete; `manage.py cleanup_files` purges after retention
        instance.versions.update(deleted_at=now)
        instance.deleted_at = now
        instance.save(update_fields=["deleted_at"])


# ---------------------------------------------------------------- versions
class VersionListCreateView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "uploads"

    def get_throttles(self):
        self.throttle_scope = "uploads" if self.request.method == "POST" else None
        return super().get_throttles()

    def get(self, request, document_id):
        doc, level = load_document(request.user, document_id)
        return Response(VersionSerializer(visible_versions(doc, level), many=True).data)

    def post(self, request, document_id):
        reject_oversized(request)
        doc, _ = load_document(request.user, document_id, min_level=OWNER)
        s = UploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        version = create_version(doc, s.validated_data["file"], request.user)
        return Response(VersionSerializer(version).data, status=status.HTTP_201_CREATED)


class VersionDownloadView(APIView):
    throttle_scope = "downloads"

    def get(self, request, document_id, version_id):
        doc, level = load_document(request.user, document_id)
        version = load_version(doc, level, version_id)
        if not can_download(request.user, version):
            raise PermissionDenied("This file isn't available for download.")
        return file_response(version)


class DownloadLinkView(APIView):
    """Short-lived signed link. Handy for browsers/<a href> where you can't set an auth header."""
    throttle_scope = "downloads"

    def post(self, request, document_id, version_id):
        doc, level = load_document(request.user, document_id)
        version = load_version(doc, level, version_id)
        if not can_download(request.user, version):
            raise PermissionDenied("This file isn't available for download.")
        token = signing.dumps({"v": str(version.id), "u": request.user.id}, salt=DOWNLOAD_SALT)
        return Response(
            {
                "url": request.build_absolute_uri(f"/api/downloads/{token}/"),
                "expires_in": settings.DOWNLOAD_LINK_TTL_SECONDS,
            }
        )


class SignedDownloadView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "downloads"

    def get(self, request, token):
        try:
            data = signing.loads(token, salt=DOWNLOAD_SALT, max_age=settings.DOWNLOAD_LINK_TTL_SECONDS)
        except signing.BadSignature:  # includes expired
            raise NotFound()
        user = User.objects.filter(pk=data["u"], is_active=True).first()
        version = (
            DocumentVersion.objects.select_related("document")
            .filter(pk=data["v"], deleted_at__isnull=True, document__deleted_at__isnull=True)
            .first()
        )
        # Re-check on redeem: access may have been revoked since the link was issued.
        if not user or not version or not can_download(user, version):
            raise NotFound()
        return file_response(version)


# ---------------------------------------------------------------- comments & review
class CommentListCreateView(APIView):
    def get(self, request, document_id, version_id):
        doc, level = load_document(request.user, document_id, min_level=Level.COMMENT)
        version = load_version(doc, level, version_id)
        return Response(CommentSerializer(version.comments.select_related("author"), many=True).data)

    def post(self, request, document_id, version_id):
        doc, level = load_document(request.user, document_id, min_level=Level.COMMENT)
        version = load_version(doc, level, version_id)
        s = CommentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        comment = s.save(version=version, author=request.user)
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class ReviewView(APIView):
    def post(self, request, document_id, version_id):
        doc, level = load_document(request.user, document_id, min_level=Level.REVIEW)
        if doc.owner_id == request.user.id and not request.user.is_superuser:
            raise PermissionDenied("You can't review your own document.")
        version = load_version(doc, level, version_id)

        s = ReviewSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        decision = s.validated_data["decision"]

        latest = doc.versions.filter(deleted_at__isnull=True).first()
        if version.pk != latest.pk:
            return Response({"detail": "Only the latest version can be reviewed."}, status=status.HTTP_409_CONFLICT)
        if version.review_status != DocumentVersion.ReviewStatus.PENDING:
            return Response({"detail": "This version was already reviewed."}, status=status.HTTP_409_CONFLICT)
        if decision == "approved" and not scan_allows_release(version):
            return Response(
                {"detail": "Version can't be approved until it passes the virus scan."},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            version.review_status = decision
            version.reviewed_by = request.user
            version.reviewed_at = timezone.now()
            version.save(update_fields=["review_status", "reviewed_by", "reviewed_at"])
            if decision == "approved":
                doc.approved_version = version
                doc.save(update_fields=["approved_version", "updated_at"])
            if s.validated_data.get("comment", "").strip():
                Comment.objects.create(version=version, author=request.user, body=s.validated_data["comment"])
        return Response(VersionSerializer(version).data)


# ---------------------------------------------------------------- per-file permissions
class AccessListCreateView(APIView):
    def get(self, request, document_id):
        doc, _ = load_document(request.user, document_id, min_level=OWNER)
        grants = doc.access_grants.select_related("user")
        return Response([{"username": g.user.username, "level": g.level, "level_name": g.get_level_display()} for g in grants])

    def post(self, request, document_id):
        doc, _ = load_document(request.user, document_id, min_level=OWNER)
        s = AccessGrantSerializer(data=request.data, context={"document": doc})
        s.is_valid(raise_exception=True)
        grant, _ = DocumentAccess.objects.update_or_create(
            document=doc, user=s.validated_data["user"],
            defaults={"level": s.validated_data["level"], "granted_by": request.user},
        )
        return Response({"username": grant.user.username, "level": grant.level}, status=status.HTTP_201_CREATED)


class AccessRevokeView(APIView):
    def delete(self, request, document_id, username):
        doc, _ = load_document(request.user, document_id, min_level=OWNER)
        deleted, _ = DocumentAccess.objects.filter(document=doc, user__username=username).delete()
        if not deleted:
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)
