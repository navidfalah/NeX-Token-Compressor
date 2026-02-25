"""
Seed built-in compression rules for languages and programming (NEX).
"""
from django.core.management.base import BaseCommand
from dashboard.models import CompressionRule


# German language compression rules
GERMAN_RULES = [
    ('Qualitätskontrollbericht', 'QKB', 'Quality control report'),
    ('Produktionscharge', 'PC', 'Production batch'),
    ('Lieferantenbewertung', 'LB', 'Supplier evaluation'),
    ('Maschinenverfügbarkeit', 'MV', 'Machine availability'),
    ('Fertigungsauftrag', 'FA', 'Manufacturing order'),
    ('Materialbedarfsplanung', 'MBP', 'Material requirements planning'),
    ('Betriebsdatenerfassung', 'BDE', 'Production data capture'),
    ('Arbeitsvorbereitung', 'AV', 'Work preparation'),
    ('Instandhaltungsmaßnahme', 'IH', 'Maintenance measure'),
    ('Stücklistenverwaltung', 'SLV', 'BOM management'),
    ('Wareneingangsprotokoll', 'WEP', 'Goods receipt protocol'),
    ('Kundenauftrag', 'KA', 'Customer order'),
    ('Bestellanforderung', 'BANF', 'Purchase requisition'),
    ('Lieferschein', 'LS', 'Delivery note'),
    ('Rechnungsprüfung', 'RP', 'Invoice verification'),
    ('Guten Tag', 'GT', 'Good day greeting'),
    ('bitte beachten Sie', 'bbS', 'Please note'),
    ('mit freundlichen Grüßen', 'mfG', 'Kind regards'),
    ('auf jeden Fall', 'ajF', 'In any case'),
    ('in Bezug auf', 'iBa', 'With regard to'),
]

# English language compression rules
ENGLISH_RULES = [
    ('Quality Control Report', 'QCR', 'Quality control report'),
    ('Production Batch Number', 'PBN', 'Production batch number'),
    ('Assembly Line', 'AL', 'Assembly line'),
    ('Key Performance Indicator', 'KPI', 'Key performance indicator'),
    ('Standard Operating Procedure', 'SOP', 'Standard operating procedure'),
    ('Bill of Materials', 'BOM', 'Bill of materials'),
    ('Enterprise Resource Planning', 'ERP', 'Enterprise resource planning'),
    ('Customer Relationship Management', 'CRM', 'Customer relationship management'),
    ('Return on Investment', 'ROI', 'Return on investment'),
    ('please find attached', 'PFA', 'Please find attached'),
    ('as per our discussion', 'APOD', 'As per our discussion'),
    ('at your earliest convenience', 'AYEC', 'At your earliest convenience'),
    ('in accordance with', 'IAW', 'In accordance with'),
    ('for your information', 'FYI', 'For your information'),
    ('as soon as possible', 'ASAP', 'As soon as possible'),
]

# NEX-style programming compression (Python)
PYTHON_NEX_RULES = [
    ('def ', 'ƒ ', 'Function definition → NEX opcode'),
    ('return ', '→ ', 'Return statement → NEX opcode'),
    ('import ', '⊕ ', 'Import statement → NEX opcode'),
    ('from ', '⊗ ', 'From import → NEX opcode'),
    ('class ', 'ℂ ', 'Class definition → NEX opcode'),
    ('if __name__ == "__main__":', '⊞MAIN:', 'Main guard → NEX opcode'),
    ('print(', '⊡(', 'Print function → NEX opcode'),
    ('for ', '∀ ', 'For loop → NEX opcode'),
    ('while ', '∃ ', 'While loop → NEX opcode'),
    ('try:', '⟦:', 'Try block → NEX opcode'),
    ('except ', '⟧ ', 'Except block → NEX opcode'),
    ('finally:', '⟨:', 'Finally block → NEX opcode'),
    ('lambda ', 'λ ', 'Lambda → NEX opcode'),
    ('assert ', '⊢ ', 'Assert → NEX opcode'),
    ('yield ', '⊣ ', 'Yield → NEX opcode'),
    ('async def ', 'ᾰƒ ', 'Async function → NEX opcode'),
    ('await ', 'ᾰ→ ', 'Await → NEX opcode'),
    ('self.', 'ₛ.', 'Self reference → NEX opcode'),
    ('None', '∅', 'None value → NEX opcode'),
    ('True', '⊤', 'True boolean → NEX opcode'),
    ('False', '⊥', 'False boolean → NEX opcode'),
]

# NEX-style programming compression (JavaScript)
JAVASCRIPT_NEX_RULES = [
    ('function ', 'ƒ ', 'Function declaration → NEX opcode'),
    ('const ', '℃ ', 'Const declaration → NEX opcode'),
    ('let ', 'ℓ ', 'Let declaration → NEX opcode'),
    ('var ', 'ν ', 'Var declaration → NEX opcode'),
    ('return ', '→ ', 'Return statement → NEX opcode'),
    ('import ', '⊕ ', 'Import → NEX opcode'),
    ('export ', '⊖ ', 'Export → NEX opcode'),
    ('async ', 'ᾰ ', 'Async → NEX opcode'),
    ('await ', 'ᾰ→ ', 'Await → NEX opcode'),
    ('console.log(', '⊡(', 'Console log → NEX opcode'),
    ('document.', '⊞.', 'Document → NEX opcode'),
    ('window.', '⊟.', 'Window → NEX opcode'),
    ('.addEventListener(', '.⊕ℓ(', 'Event listener → NEX opcode'),
    ('.querySelector(', '.⊕q(', 'Query selector → NEX opcode'),
    ('null', '∅', 'Null → NEX opcode'),
    ('undefined', '∄', 'Undefined → NEX opcode'),
    ('true', '⊤', 'True → NEX opcode'),
    ('false', '⊥', 'False → NEX opcode'),
    ('this.', 'ₛ.', 'This reference → NEX opcode'),
    ('=>', '→', 'Arrow function → NEX opcode'),
]

# SQL compression
SQL_NEX_RULES = [
    ('SELECT ', '⊕ ', 'SELECT → NEX opcode'),
    ('FROM ', '⊗ ', 'FROM → NEX opcode'),
    ('WHERE ', '⊘ ', 'WHERE → NEX opcode'),
    ('INSERT INTO ', '⊕→ ', 'INSERT INTO → NEX opcode'),
    ('UPDATE ', '⊕↑ ', 'UPDATE → NEX opcode'),
    ('DELETE FROM ', '⊕✗ ', 'DELETE FROM → NEX opcode'),
    ('JOIN ', '⊕⊗ ', 'JOIN → NEX opcode'),
    ('LEFT JOIN ', '⊕⊗← ', 'LEFT JOIN → NEX opcode'),
    ('RIGHT JOIN ', '⊕⊗→ ', 'RIGHT JOIN → NEX opcode'),
    ('INNER JOIN ', '⊕⊗↔ ', 'INNER JOIN → NEX opcode'),
    ('GROUP BY ', '⊕⊕ ', 'GROUP BY → NEX opcode'),
    ('ORDER BY ', '⊕↕ ', 'ORDER BY → NEX opcode'),
    ('HAVING ', '⊕⊘ ', 'HAVING → NEX opcode'),
    ('CREATE TABLE ', '⊕ℂ ', 'CREATE TABLE → NEX opcode'),
    ('ALTER TABLE ', '⊕Δ ', 'ALTER TABLE → NEX opcode'),
]


class Command(BaseCommand):
    help = 'Seed built-in compression rules for languages and programming (NEX)'

    def handle(self, *args, **options):
        created = 0

        # German
        for pattern, replacement, desc in GERMAN_RULES:
            _, was_created = CompressionRule.objects.get_or_create(
                pattern=pattern, replacement=replacement, is_system=True,
                defaults={
                    'rule_type': CompressionRule.TYPE_BUILTIN_LANGUAGE,
                    'language': CompressionRule.LANG_DE,
                    'description': desc,
                    'is_active': True,
                }
            )
            if was_created:
                created += 1

        # English
        for pattern, replacement, desc in ENGLISH_RULES:
            _, was_created = CompressionRule.objects.get_or_create(
                pattern=pattern, replacement=replacement, is_system=True,
                defaults={
                    'rule_type': CompressionRule.TYPE_BUILTIN_LANGUAGE,
                    'language': CompressionRule.LANG_EN,
                    'description': desc,
                    'is_active': True,
                }
            )
            if was_created:
                created += 1

        # Python (NEX)
        for pattern, replacement, desc in PYTHON_NEX_RULES:
            _, was_created = CompressionRule.objects.get_or_create(
                pattern=pattern, replacement=replacement, is_system=True,
                defaults={
                    'rule_type': CompressionRule.TYPE_BUILTIN_PROGRAMMING,
                    'programming_language': CompressionRule.PROG_PYTHON,
                    'description': desc,
                    'is_active': True,
                }
            )
            if was_created:
                created += 1

        # JavaScript (NEX)
        for pattern, replacement, desc in JAVASCRIPT_NEX_RULES:
            _, was_created = CompressionRule.objects.get_or_create(
                pattern=pattern, replacement=replacement, is_system=True,
                defaults={
                    'rule_type': CompressionRule.TYPE_BUILTIN_PROGRAMMING,
                    'programming_language': CompressionRule.PROG_JAVASCRIPT,
                    'description': desc,
                    'is_active': True,
                }
            )
            if was_created:
                created += 1

        # SQL (NEX)
        for pattern, replacement, desc in SQL_NEX_RULES:
            _, was_created = CompressionRule.objects.get_or_create(
                pattern=pattern, replacement=replacement, is_system=True,
                defaults={
                    'rule_type': CompressionRule.TYPE_BUILTIN_PROGRAMMING,
                    'programming_language': CompressionRule.PROG_SQL,
                    'description': desc,
                    'is_active': True,
                }
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Successfully seeded {created} compression rules '
            f'(DE: {len(GERMAN_RULES)}, EN: {len(ENGLISH_RULES)}, '
            f'Python: {len(PYTHON_NEX_RULES)}, JS: {len(JAVASCRIPT_NEX_RULES)}, '
            f'SQL: {len(SQL_NEX_RULES)})'
        ))
