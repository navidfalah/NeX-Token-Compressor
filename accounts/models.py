"""
Firma-KI Accounts — Models
Multi-tenant Organization + Custom User with RBAC roles.
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class Organization(models.Model):
    """
    A tenant organization. All data is scoped to an Organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Custom User model with Organization membership and role-based access.
    """
    ROLE_OWNER = 'owner'
    ROLE_EDITOR = 'editor'
    ROLE_VIEWER = 'viewer'
    ROLE_USER = 'user' # Legacy fallback
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Organization Owner'),
        (ROLE_EDITOR, 'Editor'),
        (ROLE_VIEWER, 'Viewer'),
        (ROLE_USER, 'Organization User'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='members',
        null=True,
        blank=True,
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_USER)
    last_activity = models.DateTimeField(null=True, blank=True, help_text='Last activity timestamp')

    class Meta:
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_owner(self):
        return self.role == self.ROLE_OWNER

    @property
    def is_org_user(self):
        return self.role in [self.ROLE_USER, self.ROLE_EDITOR, self.ROLE_VIEWER]
        
    @property
    def is_editor(self):
        return self.role in [self.ROLE_OWNER, self.ROLE_EDITOR, self.ROLE_USER]


class Invitation(models.Model):
    """
    Invitation for a new user to join an organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    token = models.UUIDField(default=uuid.uuid4, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invite {self.email} → {self.organization.name}"
