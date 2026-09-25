from django.contrib import admin
from .models import User
from django.contrib.auth.admin import UserAdmin

# Register your models here.
@admin.register(User)
class PortalUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Portal", {"fields": ("role",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Portal", {"fields": ("role",)}),)
    list_display = ("username", "role", "is_staff")