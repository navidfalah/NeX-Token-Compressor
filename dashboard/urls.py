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
    path('team/', views.team_management, name='team'),
    path('audit/', views.audit_list, name='audit_list'),
    path('audit/<uuid:log_id>/', views.audit_detail, name='audit_detail'),
    path('api/live-stats/', views.api_live_stats, name='api_live_stats'),
    path('playground/', views.playground, name='playground'),
    path('security-audit/', views.security_audit, name='security_audit'),
    path('mcp-tools/', views.mcp_tools, name='mcp_tools'),
    path('edge-nodes/', views.edge_nodes, name='edge_nodes'),
]
