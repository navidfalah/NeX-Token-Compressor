"""
Firma-KI Accounts — Forms
Registration, Login, and Invite forms.
"""
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.text import slugify
from .models import User, Organization, Invitation


class RegistrationForm(forms.Form):
    """
    Creates a new Organization + Owner user in one step.
    """
    organization_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'Your Company Name',
        }),
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'Username',
        }),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'you@company.com',
        }),
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'First Name',
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'Last Name',
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': '••••••••',
        }),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': '••••••••',
        }),
    )

    def clean_organization_name(self):
        name = self.cleaned_data['organization_name']
        slug = slugify(name)
        if Organization.objects.filter(slug=slug).exists():
            raise forms.ValidationError('An organization with this name already exists.')
        return name

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data

    def save(self):
        data = self.cleaned_data
        org = Organization.objects.create(
            name=data['organization_name'],
            slug=slugify(data['organization_name']),
        )
        user = User.objects.create_user(
            username=data['username'],
            email=data['email'],
            password=data['password'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            organization=org,
            role=User.ROLE_OWNER,
        )
        return user


class LoginForm(AuthenticationForm):
    """
    Styled login form.
    """
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'Username',
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': '••••••••',
        }),
    )


class InviteForm(forms.Form):
    """
    Invite a new user to the organization.
    """
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'colleague@company.com',
        }),
    )
    role = forms.ChoiceField(
        choices=[(User.ROLE_EDITOR, 'Editor'), (User.ROLE_VIEWER, 'Viewer')],
        initial=User.ROLE_VIEWER,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
        })
    )


class AcceptInviteForm(forms.Form):
    """
    Form for an invited user to set their credentials.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'Username',
        }),
    )
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'First Name',
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': 'Last Name',
        }),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': '••••••••',
        }),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800/50 border border-slate-600 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-300',
            'placeholder': '••••••••',
        }),
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError('Passwords do not match.')
        return cleaned_data
