import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.template import Template, Context
print(Template('filename: {{ \n docs \n }}').render(Context({'docs': 'hello'})))
