"""
URL configuration for Firma-KI project.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', TemplateView.as_view(template_name='landing.html'), name='landing'),
    path('', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('v1/', include('gateway.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

