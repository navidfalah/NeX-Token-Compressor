import os
import django
from django.template.loader import get_template
import glob

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

errors = 0
for filepath in glob.glob('templates/**/*.html', recursive=True):
    template_name = filepath.replace('templates/', '', 1)
    try:
        get_template(template_name)
    except Exception as e:
        print(f"Error in {template_name}: {e.__class__.__name__} - {e}")
        errors += 1

if errors == 0:
    print("All templates parsed successfully!")
