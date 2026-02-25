from django.core.management.base import BaseCommand
from dashboard.models import AIProvider

class Command(BaseCommand):
    help = 'Seed the default Firma-KI System AI (DeepSeek) provider with the authorized global API key'

    def handle(self, *args, **options):
        provider, created = AIProvider.objects.get_or_create(
            is_system=True,
            provider_type=AIProvider.PROVIDER_DEEPSEEK,
            defaults={
                'name': 'Firma-KI AI (DeepSeek)',
                'model_name': 'deepseek-chat',
                'api_key': 'sk-3ffe6ba4ac8a435d9630d7855d9d9f34',
                'api_base_url': 'https://api.deepseek.com/chat/completions',
                'is_active': True,
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS('Successfully created default Firma-KI System AI (DeepSeek) Provider.'))
        else:
            # Always ensure the API key is up to date
            provider.api_key = 'sk-3ffe6ba4ac8a435d9630d7855d9d9f34'
            provider.save()
            self.stdout.write(self.style.SUCCESS('Default Firma-KI System AI already exists; updated API key.'))
