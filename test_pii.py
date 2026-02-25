import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from gateway.pii_masker import PIIMasker
from dashboard.models import PIIConfig

class MockConfig:
    mask_names = True
    mask_emails = True
    mask_ibans = True
    mask_ips = True
    mask_phone_numbers = True
    custom_regex_patterns = ""

masker = PIIMasker(MockConfig())

tests = [
    "Sustainability Dimensions",
    "Advanced Text",
    "Unsupervised Learning",
    "Software Engineer",
    "Integration Web",
    "Circular Cities",
    "Siegen Entwicklung",
    "Allgemeine Hochschulreife",
    "Technische Leitung",
    "Backend Developer",
    "Navid Falah",
    "John Doe",
    "Alan Turing",
    "Angela Merkel",
    "2024",
    ". 2021",
    "My email is Navid.Falah@student.uni-siegen.de",
    "Call me at +49 176 1234 5678"
]

print("--- PII MASKER TEST ---")
for t in tests:
    masked, mapping = masker.mask(t)
    if mapping:
        print(f"MASKED: '{t}' -> '{masked}' (Mappings: {mapping})")
    else:
        print(f"CLEAN:  '{t}' -> '{masked}'")
