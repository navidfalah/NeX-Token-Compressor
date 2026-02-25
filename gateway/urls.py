"""
Firma-KI Gateway — URL Configuration
"""
from django.urls import path
from .views import ChatCompletionsView

app_name = 'gateway'

urlpatterns = [
    path('chat/completions', ChatCompletionsView.as_view(), name='chat_completions'),
]
