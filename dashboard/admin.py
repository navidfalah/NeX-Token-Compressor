"""
Firma-KI Dashboard — Admin Configuration
"""
from django.contrib import admin
from .models import APIKey, CompressionRule, PIIConfig, AuditLog


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'user', 'masked_key', 'is_active', 'created_at', 'last_used_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('name', 'key')
    readonly_fields = ('key',)


@admin.register(CompressionRule)
class CompressionRuleAdmin(admin.ModelAdmin):
    list_display = ('pattern', 'replacement', 'organization', 'is_active', 'created_at')
    list_filter = ('is_active', 'organization')
    search_fields = ('pattern', 'replacement')


@admin.register(PIIConfig)
class PIIConfigAdmin(admin.ModelAdmin):
    list_display = ('organization', 'mask_names', 'mask_emails', 'mask_ibans', 'mask_ips')
    list_filter = ('mask_names', 'mask_emails')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'organization', 'status', 'tokens_original', 'tokens_compressed', 'cost_saved', 'cache_hit', 'latency_ms')
    list_filter = ('status', 'cache_hit', 'organization')
    search_fields = ('original_payload',)
    readonly_fields = ('original_payload', 'compressed_payload', 'deepseek_response', 'final_response')
