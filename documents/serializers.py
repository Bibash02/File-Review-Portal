from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Comment, Document, DocumentVersion, Level
from .permissions import LEVEL_NAMES, access_level
from .validators import validate_upload

User = get_user_model()


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField(validators=[validate_upload], max_length=255)


class DocumentCreateSerializer(UploadSerializer):
    title = serializers.CharField(max_length=200)


class VersionSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.CharField(source="uploaded_by.username", read_only=True)
    reviewed_by = serializers.CharField(source="reviewed_by.username", read_only=True)

    class Meta:
        model = DocumentVersion
        fields = [
            "id", "version_number", "original_name", "content_type", "size", "sha256",
            "scan_status", "review_status", "uploaded_by", "reviewed_by", "reviewed_at", "created_at",
        ]


class DocumentSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.username", read_only=True)
    approved_version = VersionSerializer(read_only=True)
    latest_version = serializers.SerializerMethodField()
    my_access = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "title", "owner", "approved_version", "latest_version", "my_access", "created_at", "updated_at"]

    def _level(self, doc):
        return access_level(self.context["request"].user, doc)

    def get_my_access(self, doc):
        return LEVEL_NAMES.get(self._level(doc))

    def get_latest_version(self, doc):
        if self._level(doc) < Level.REVIEW:
            return None  # view/comment grantees only ever see the approved version
        v = doc.versions.filter(deleted_at__isnull=True).first()
        return VersionSerializer(v).data if v else None


class CommentSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="author.username", read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "author", "body", "created_at"]
        read_only_fields = ["id", "author", "created_at"]


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["approved", "rejected"])
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        if attrs["decision"] == "rejected" and not attrs.get("comment", "").strip():
            raise serializers.ValidationError({"comment": "Explain why you're rejecting this version."})
        return attrs


class AccessGrantSerializer(serializers.Serializer):
    username = serializers.CharField()
    level = serializers.ChoiceField(choices=Level.choices)

    def validate(self, attrs):
        document = self.context["document"]
        user = User.objects.filter(username=attrs["username"], is_active=True).first()
        if not user:
            raise serializers.ValidationError({"username": "User not found."})
        if user.id == document.owner_id:
            raise serializers.ValidationError({"username": "Owner already has full access."})
        if attrs["level"] == Level.REVIEW and user.role != User.Role.REVIEWER and not user.is_superuser:
            raise serializers.ValidationError({"level": "Only users with the reviewer role can get review access."})
        attrs["user"] = user
        return attrs
