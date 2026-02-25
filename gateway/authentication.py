"""
Firma-KI Gateway — API Key Authentication
Validates Bearer tokens against the APIKey model.
"""
from dashboard.models import APIKey
from django.utils import timezone


class APIKeyAuthenticationError(Exception):
    pass


def authenticate_api_key(request):
    """
    Extract and validate the API key from the Authorization header.
    Returns (api_key, organization) tuple.
    Raises APIKeyAuthenticationError on failure.
    """
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')

    if not auth_header.startswith('Bearer '):
        raise APIKeyAuthenticationError('Missing or invalid Authorization header. Use: Bearer <api_key>')

    key_value = auth_header[7:].strip()

    try:
        api_key = APIKey.objects.select_related('organization', 'user').get(
            key=key_value,
            is_active=True,
        )
    except APIKey.DoesNotExist:
        raise APIKeyAuthenticationError('Invalid or revoked API key.')

    # Update last used timestamp
    api_key.last_used_at = timezone.now()
    api_key.save(update_fields=['last_used_at'])

    return api_key, api_key.organization
