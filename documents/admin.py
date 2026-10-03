from django.contrib import admin
from .models import Document, DocumentVersion, Comment, DocumentAccess, Level 

# Register your models here.
@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "approved_version", "created_at", "updated_at")
    search_fields = ("title", "owner__username")
    list_filter = ("created_at", "updated_at")

@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "version_number", "original_name", "content_type", "size", "sha256", "scan_status", "review_status", "uploaded_by", "reviewed_by", "reviewed_at", "created_at")
    search_fields = ("document__title", "original_name", "uploaded_by__username")
    list_filter = ("scan_status", "review_status", "created_at")

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "version", "author", "body", "created_at")
    search_fields = ("version__document__title", "author__username", "body")
    list_filter = ("created_at",)

@admin.register(DocumentAccess)
class DocumentAccessAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "user", "level", "granted_by", "created_at")
    search_fields = ("document__title", "user__username", "granted_by__username")
    list_filter = ("level", "created_at")

# @admin.register(Level)
# class LevelAdmin(admin.ModelAdmin):
#     list_display = ("id", "name", "description")
#     search_fields = ("name", "description")
