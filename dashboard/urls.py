"""
Firma-KI Dashboard — URL Configuration
"""
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
    path('api-keys/', views.api_key_list, name='api_keys'),
    path('ai-providers/', views.ai_providers, name='ai_providers'),
    path('rules/', views.compression_rules, name='rules'),
    path('privacy/', views.privacy_hub, name='privacy'),
    path('files/', views.file_analysis, name='file_analysis'),
    path('team/', views.team_management, name='team'),
    path('audit/', views.audit_list, name='audit_list'),
    path('audit/<uuid:log_id>/', views.audit_detail, name='audit_detail'),
    path('api/live-stats/', views.api_live_stats, name='api_live_stats'),
    path('api/file-chat/<uuid:file_id>/', views.api_file_chat, name='api_file_chat'),
    path('chat/', views.secure_chat, name='secure_chat'),
    path('api/secure-chat/', views.api_secure_chat, name='api_secure_chat'),
    path('api/chat-history/', views.api_chat_history, name='api_chat_history'),
    path('api/chat-delete/', views.api_chat_delete, name='api_chat_delete'),
    path('api/chat-update/', views.api_chat_update, name='api_chat_update'),
    path('playground/', views.playground, name='playground'),
    path('security-audit/', views.security_audit, name='security_audit'),
    path('secure-documents/', views.masked_documents_list, name='masked_documents_list'),
    path('secure-documents/<uuid:doc_id>/', views.masked_document_chat, name='masked_document_chat'),
    path('secure-documents/<uuid:doc_id>/download/text/', views.masked_document_download_text, name='masked_document_download_text'),
    path('secure-documents/<uuid:doc_id>/download/pdf/', views.masked_document_download_pdf, name='masked_document_download_pdf'),
    path('secure-documents/<uuid:doc_id>/preview/text/', views.masked_document_preview_text, name='masked_document_preview_text'),
    path('secure-documents/<uuid:doc_id>/preview/pdf/', views.masked_document_preview_pdf, name='masked_document_preview_pdf'),
    path('api/secure-documents/<uuid:doc_id>/chat/', views.api_masked_document_chat, name='api_masked_document_chat'),
]
