import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from dashboard.models import AIProvider

system_provider = AIProvider.objects.filter(is_system=True, provider_type='deepseek').first()
if system_provider:
    system_provider.api_key = 'sk-3ffe6ba4ac8a435d9630d7855d9d9f34'
    system_provider.save()
    print("Successfully updated the system DeepSeek API key.")
else:
    print("Could not find the system DeepSeek provider.")
