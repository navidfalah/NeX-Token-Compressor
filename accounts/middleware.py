"""
Firma-KI Accounts — Middleware
Attaches Organization context to every authenticated request.
"""


class OrganizationMiddleware:
    """
    Sets request.organization from the authenticated user's organization.
    This enables all views and querysets to scope data by tenant.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            request.organization = request.user.organization
        response = self.get_response(request)
        return response
