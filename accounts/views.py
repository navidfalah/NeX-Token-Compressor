"""
Firma-KI Accounts — Views
Registration, Login, Logout, and Team Invite views.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import RegistrationForm, LoginForm, InviteForm, AcceptInviteForm
from .models import Invitation, User
from .decorators import owner_required


def register_view(request):
    """Register a new organization and owner account."""
    if request.user.is_authenticated:
        return redirect('dashboard:home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to Firma-KI, {user.first_name}! Your organization has been created.')
            return redirect('dashboard:home')
    else:
        form = RegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    """Log in an existing user."""
    if request.user.is_authenticated:
        return redirect('dashboard:home')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name}!')
            next_url = request.GET.get('next', 'dashboard:home')
            return redirect(next_url)
    else:
        form = LoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """Log out the current user."""
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('landing')


@login_required
@owner_required
def invite_user_view(request):
    """Owner invites a new team member."""
    if request.method == 'POST':
        form = InviteForm(request.POST)
        if form.is_valid():
            invitation = Invitation.objects.create(
                organization=request.user.organization,
                email=form.cleaned_data['email'],
                invited_by=request.user,
            )
            from django.core.cache import cache
            cache.set(f"invite_role_{invitation.token}", form.cleaned_data['role'], timeout=86400 * 7)
            messages.success(request, f'Invitation sent to {invitation.email}.')
            return redirect('dashboard:home')
    else:
        form = InviteForm()

    return render(request, 'accounts/invite.html', {'form': form})


def accept_invite_view(request, token):
    """Accept an invitation and create an account."""
    invitation = get_object_or_404(Invitation, token=token, accepted=False)

    if request.method == 'POST':
        form = AcceptInviteForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            from django.core.cache import cache
            assigned_role = cache.get(f"invite_role_{invitation.token}", User.ROLE_VIEWER)
            
            user = User.objects.create_user(
                username=data['username'],
                email=invitation.email,
                password=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                organization=invitation.organization,
                role=assigned_role,
            )
            invitation.accepted = True
            invitation.save()
            login(request, user)
            messages.success(request, f'Welcome to {invitation.organization.name}!')
            return redirect('dashboard:home')
    else:
        form = AcceptInviteForm()

    return render(request, 'accounts/accept_invite.html', {
        'form': form,
        'invitation': invitation,
    })
