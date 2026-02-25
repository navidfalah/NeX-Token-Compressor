"""
Firma-KI Accounts — Decorators
RBAC enforcement decorators.
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def owner_required(view_func):
    """Restrict a view to organization owners only."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not request.user.is_owner:
            messages.error(request, 'This action requires Owner permissions.')
            return redirect('dashboard:home')
        return view_func(request, *args, **kwargs)
    return wrapper
