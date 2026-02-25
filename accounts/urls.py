"""
Firma-KI Accounts — URL Configuration
"""
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('invite/', views.invite_user_view, name='invite'),
    path('invite/accept/<uuid:token>/', views.accept_invite_view, name='accept_invite'),
]
