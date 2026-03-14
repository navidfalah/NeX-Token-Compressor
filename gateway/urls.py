"""
Firma-KI Gateway — URL Configuration
"""
from django.urls import path
from .views import ChatCompletionsView
from .mcp.views import MCPExecuteView

app_name = 'gateway'

urlpatterns = [
    path('chat/completions', ChatCompletionsView.as_view(), name='chat_completions'),
    path('mcp/execute', MCPExecuteView.as_view(), name='mcp_execute'),
]
