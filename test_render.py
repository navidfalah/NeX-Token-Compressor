import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.template.loader import render_to_string
from dashboard.models import MaskedDocument, PIIConfig
from accounts.models import Organization

org = Organization.objects.first()
docs = MaskedDocument.objects.filter(organization=org)
    
html = render_to_string('dashboard/masked_documents_list.html', {'documents': docs})

if '{{ document.filename }}' in html:
    print("YES, literal found!")
else:
    print("NO, literal not found!")

if '{{ document.file_size' in html:
    print("YES, literal file_size found!")

if 'more' in html:
    print("More found!")
