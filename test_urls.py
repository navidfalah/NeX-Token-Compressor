import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import Client
from accounts.models import User

c = Client()
u = User.objects.first()
if not u:
    print("No users found!")
else:
    c.force_login(u)
    urls = [
        '/dashboard/audit/',
        '/dashboard/privacy/',
        '/dashboard/ai-providers/',
        '/dashboard/team/',
    ]
    for url in urls:
        print(f"Testing {url}...")
        try:
            r = c.get(url)
            if r.status_code != 200:
                print(f"  Returned {r.status_code}")
            else:
                print(f"  OK")
        except Exception as e:
            print(f"  EXCEPTION: {e.__class__.__name__}: {e}")
