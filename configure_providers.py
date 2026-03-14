import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from dashboard.models import AIProvider, CascadeConfig
from accounts.models import Organization

org = Organization.objects.first()

gemini_provider = AIProvider.objects.filter(provider_type='gemini', organization=org).first()
if not gemini_provider:
    gemini_provider = AIProvider.objects.create(
        organization=org,
        name='Gemini PRO API (Heavy Logic)',
        provider_type='gemini',
        api_base_url='https://generativelanguage.googleapis.com/v1beta/models/',
        api_key='AIzaSyCVwClfpS71NkDCsH_0FeU0tusQpP2bwMo',
        model_name='gemini-1.5-pro',
        is_active=True
    )
    print("Created Gemini Provider.")
else:
    gemini_provider.api_key = 'AIzaSyCVwClfpS71NkDCsH_0FeU0tusQpP2bwMo'
    gemini_provider.save()
    print("Updated Gemini Provider API key.")

deepseek_provider = AIProvider.objects.filter(provider_type='deepseek', organization=org).first()
if not deepseek_provider:
    deepseek_provider = AIProvider.objects.filter(provider_type='deepseek').first()

if not deepseek_provider:
    print("No DeepSeek provider found! Creating one.")
    deepseek_provider = AIProvider.objects.create(
        organization=org,
        name='DeepSeek API (Standard Routing)',
        provider_type='deepseek',
        api_base_url='https://api.deepseek.com/v1',
        api_key='sk-d25091a148a04c1aa3eeabaffebda4c0', # using previous one or dummy if not needed
        model_name='deepseek-chat',
        is_active=True
    )
    
# Create or update Cascade Config
cascade, created = CascadeConfig.objects.get_or_create(organization=org)
cascade.is_enabled = True
cascade.cheap_provider = deepseek_provider
cascade.heavyweight_provider = gemini_provider
cascade.uncertainty_threshold = 0.5
cascade.save()

print(f"Cascade Config active: {cascade.is_enabled}")
print(f"Cheap: {cascade.cheap_provider.name}")
print(f"Heavy: {cascade.heavyweight_provider.name}")
