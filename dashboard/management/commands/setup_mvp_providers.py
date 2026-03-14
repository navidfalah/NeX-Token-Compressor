from django.core.management.base import BaseCommand
from dashboard.models import AIProvider, CascadeConfig
from accounts.models import Organization

class Command(BaseCommand):
    help = 'Sets up default AI Providers (DeepSeek and Gemini) for MVP Cascade Routing.'

    def handle(self, *args, **kwargs):
        org = Organization.objects.first()
        if not org:
            self.stdout.write(self.style.ERROR('No organization found. Please register an account first.'))
            return

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
            self.stdout.write(self.style.SUCCESS('Created Gemini Provider.'))
        else:
            gemini_provider.api_key = 'AIzaSyCVwClfpS71NkDCsH_0FeU0tusQpP2bwMo'
            gemini_provider.save()
            self.stdout.write(self.style.SUCCESS('Updated Gemini Provider API key.'))

        deepseek_provider = AIProvider.objects.filter(provider_type='deepseek', organization=org).first()
        if not deepseek_provider:
            deepseek_provider = AIProvider.objects.filter(provider_type='deepseek').first()

        if not deepseek_provider:
            deepseek_provider = AIProvider.objects.create(
                organization=org,
                name='DeepSeek API (Standard Routing)',
                provider_type='deepseek',
                api_base_url='https://api.deepseek.com/v1',
                api_key='sk-d25091a148a04c1aa3eeabaffebda4c0',
                model_name='deepseek-chat',
                is_active=True
            )
            self.stdout.write(self.style.SUCCESS('Created DeepSeek Provider.'))
            
        # Create or update Cascade Config
        cascade, created = CascadeConfig.objects.get_or_create(organization=org)
        cascade.is_enabled = True
        cascade.cheap_provider = deepseek_provider
        cascade.heavyweight_provider = gemini_provider
        cascade.uncertainty_threshold = 0.5
        cascade.save()

        self.stdout.write(self.style.SUCCESS(f'Cascade Config active: {cascade.is_enabled}'))
        self.stdout.write(self.style.SUCCESS(f'Cheap Provider: {cascade.cheap_provider.name}'))
        self.stdout.write(self.style.SUCCESS(f'Heavy Provider: {cascade.heavyweight_provider.name}'))
