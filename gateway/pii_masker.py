"""
Firma-KI Gateway — PII Masker
GDPR-compliant PII detection and masking before data reaches DeepSeek.
"""
import re
import uuid


class PIIMasker:
    """
    Masks PII in text based on organization's PIIConfig.
    Stores a mapping for re-injection after processing.
    """

    # Standard PII patterns
    PATTERNS = {
        'emails': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'ibans': r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b',
        'ips': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        'phone_numbers': r'\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?[\d\-.\s]{6,15}\b',
        'names': r'\b[A-Z][a-z]+\s[A-Z][a-z]+\b',  # Simple name pattern
    }

    def __init__(self, pii_config=None):
        self.config = pii_config
        self.mask_map = {}  # Maps placeholders back to original values
        self._counter = 0

    def _generate_placeholder(self, pii_type):
        """Generate a unique placeholder token."""
        self._counter += 1
        return f"[{pii_type.upper()}_{self._counter}]"

    def mask(self, text):
        """
        Mask PII in text according to the organization's config.
        Returns (masked_text, mask_map).
        """
        if not self.config:
            return text, {}

        self.mask_map = {}
        masked_text = text

        def validate_phone(val):
            return sum(c.isdigit() for c in val) >= 7

        NON_NAME_WORDS = {
            'software', 'engineer', 'developer', 'frontend', 'backend', 'fullstack', 
            'manager', 'director', 'lead', 'senior', 'junior', 'advanced', 
            'learning', 'text', 'sustainability', 'dimensions', 'integration', 
            'web', 'circular', 'cities', 'siegen', 'entwicklung', 'indicator', 
            'allgemeine', 'hochschulreife', 'technische', 'leitung', 'project',
            'management', 'science', 'computer', 'data', 'analyst', 'designer',
            'marketing', 'sales', 'product', 'owner', 'scrum', 'master', 'agile',
            'coach', 'business', 'finance', 'accounting', 'hr', 'human', 'resources',
            'consulting', 'consultant', 'associate', 'partner', 'principal', 'specialist',
            'technician', 'administration', 'administrator', 'support', 'quality', 'assurance',
            'qa', 'testing', 'operations', 'logistics', 'supply', 'chain', 'legal', 'counsel',
            'assistant', 'executive', 'chief', 'officer', 'ceo', 'cto', 'cfo', 'coo', 'cmo',
            'cio', 'ciso', 'vp', 'president', 'representative', 'coordinator', 'student',
            'intern', 'bachelor', 'master', 'phd', 'diploma', 'degree', 'university',
            'college', 'school', 'institute', 'academy', 'department', 'faculty', 'laboratory',
            'research', 'thesis', 'dissertation', 'grade', 'gpa', 'semester', 'course',
            'module', 'exam', 'certificate', 'certification', 'training', 'workshop',
            'seminar', 'portfolio', 'skill', 'language', 'english', 'german', 'french',
            'spanish', 'italian', 'python', 'java', 'javascript', 'html', 'css', 'sql',
            'database', 'cloud', 'aws', 'azure', 'gcp', 'devops', 'docker', 'kubernetes',
            'linux', 'windows', 'macos', 'git', 'jira', 'confluence', 'office', 'word',
            'excel', 'powerpoint', 'communication', 'teamwork', 'leadership', 'problem',
            'solving', 'analytical', 'creative', 'flexible', 'motivated', 'proactive',
            'independent', 'reliable', 'organized', 'detail', 'oriented', 'customer',
            'client', 'stakeholder', 'unsupervised', 'ai', 'machine', 'deep', 'nlp',
            'vision', 'robotics', 'automation', 'test', 'development', 'design', 'ui', 'ux',
            'interface', 'experience', 'user', 'interface', 'system', 'network', 'security',
            'cybersecurity', 'infrastructure', 'architecture', 'architect', 'hardware',
            'electronics', 'electrical', 'mechanical', 'civil', 'industrial', 'manufacturing'
        }
        
        def validate_name(val):
            words = val.lower().split()
            # If the user's name is actually exactly two words and one is a blacklist word, don't mask.
            # E.g. "Software Engineer" -> both are in blacklist? Actually just ANY blacklist word rejects it.
            for w in words:
                if w in NON_NAME_WORDS:
                    return False
            return True

        # Apply standard patterns
        if self.config.mask_emails:
            masked_text = self._mask_pattern(masked_text, self.PATTERNS['emails'], 'EMAIL')

        if self.config.mask_ibans:
            masked_text = self._mask_pattern(masked_text, self.PATTERNS['ibans'], 'IBAN')

        if self.config.mask_ips:
            masked_text = self._mask_pattern(masked_text, self.PATTERNS['ips'], 'IP')

        if self.config.mask_phone_numbers:
            masked_text = self._mask_pattern(masked_text, self.PATTERNS['phone_numbers'], 'PHONE', validator=validate_phone)

        if self.config.mask_names:
            try:
                import scrubadub
                scrubber = scrubadub.Scrubber()
                # Remove detectors we don't want interfering
                scrubber.remove_detector('email')
                scrubber.remove_detector('phone')
                scrubber.remove_detector('url')
                scrubber.remove_detector('credential')
                scrubber.remove_detector('postalcode')
                scrubber.remove_detector('ssn')
                scrubber.remove_detector('twitter')
                
                # We need scrubadub to give us the replaced text, but with our custom placeholders
                # To do this safely, we find names and manually replace them
                for fil in scrubber.iter_filth(masked_text):
                    if fil.type == 'name':
                        original_name = fil.text
                        if validate_name(original_name):
                            placeholder = self._generate_placeholder('NAME')
                            self.mask_map[placeholder] = original_name
                            masked_text = masked_text.replace(original_name, placeholder)
            except ImportError:
                # Fallback if scrubadub isn't installed
                masked_text = self._mask_pattern(masked_text, self.PATTERNS['names'], 'NAME', validator=validate_name)

        # Apply custom regex patterns
        if self.config.custom_regex_patterns:
            for line in self.config.custom_regex_patterns.strip().split('\n'):
                if '|||' in line:
                    pattern, replacement_label = line.split('|||', 1)
                    masked_text = self._mask_pattern(
                        masked_text, pattern.strip(), replacement_label.strip()
                    )

        return masked_text, self.mask_map

    def _mask_pattern(self, text, pattern, pii_type, validator=None):
        """Replace all matches of a pattern with placeholders."""
        def replacer(match):
            original = match.group(0)
            if validator and not validator(original):
                return original
            placeholder = self._generate_placeholder(pii_type)
            self.mask_map[placeholder] = original
            return placeholder

        try:
            return re.sub(pattern, replacer, text)
        except re.error:
            return text  # Skip invalid patterns gracefully

    def unmask(self, text, mask_map=None):
        """
        Re-inject original PII values from placeholders.
        """
        mapping = mask_map or self.mask_map
        result = text
        for placeholder, original in mapping.items():
            result = result.replace(placeholder, original)
        return result
