from django.template.loader import render_to_string
from dashboard.models import MaskedDocument
from accounts.models import Organization

org = Organization.objects.first()
docs = MaskedDocument.objects.filter(organization=org)
html = render_to_string('dashboard/masked_documents_list.html', {'documents': docs})

with open('debug_output.html', 'w') as f:
    f.write(html)

print("RENDER SUCCESS. Wrote to debug_output.html")
print("Filename output inside html:")
for line in html.split('\n'):
    if 'document.filename' in line:
        print(">>>", line)
