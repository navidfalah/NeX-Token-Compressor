"""
Firma-KI Accounts — Admin Configuration
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Organization, User, Invitation


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'organization', 'role', 'is_active')
    list_filter = ('role', 'is_active', 'organization')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Firma-KI', {'fields': ('organization', 'role')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Firma-KI', {'fields': ('organization', 'role')}),
    )


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'organization', 'invited_by', 'accepted', 'created_at')
    list_filter = ('accepted', 'organization')
