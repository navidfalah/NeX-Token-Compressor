"""
Firma-KI Dashboard — Models
API Keys, AI Providers, Compression Rules, PII Config, File Analysis, and Audit Logs.
"""
import uuid
import secrets
from django.db import models
from django.conf import settings


class APIKey(models.Model):
    """
    Scoped API key for a user within an organization.
    Used to authenticate gateway requests.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='api_keys'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_keys'
    )
    name = models.CharField(max_length=100, help_text='A friendly name for this key')
    key = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    # Policy settings
    linked_provider = models.ForeignKey(
        'AIProvider', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='api_keys',
        help_text='Force this key to route through a specific AI provider'
    )
    rate_limit = models.IntegerField(
        default=60,
        help_text='Max requests per minute (0 = unlimited)'
    )
    daily_token_limit = models.IntegerField(
        default=0,
        help_text='Max tokens per day (0 = unlimited)'
    )
    allowed_models = models.CharField(
        max_length=500, blank=True, default='',
        help_text='Comma-separated list of allowed model names (empty = all models)'
    )
    enable_compression = models.BooleanField(
        default=True, help_text='Apply compression rules to requests using this key'
    )
    enable_pii_masking = models.BooleanField(
        default=True, help_text='Apply PII masking to requests using this key'
    )
    enable_caching = models.BooleanField(
        default=True, help_text='Enable semantic caching for this key'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'API Key'
        verbose_name_plural = 'API Keys'

    def __str__(self):
        return f"{self.name} ({self.key[:8]}...)"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = f"fk-{secrets.token_hex(28)}"
        super().save(*args, **kwargs)

    @property
    def masked_key(self):
        return f"{self.key[:8]}...{self.key[-4:]}"


class AIProvider(models.Model):
    """
    Configurable AI provider for an organization.
    Supports DeepSeek, OpenAI, Gemini, Grok, Anthropic, custom etc.
    """
    PROVIDER_DEEPSEEK = 'deepseek'
    PROVIDER_OPENAI = 'openai'
    PROVIDER_GEMINI = 'gemini'
    PROVIDER_GROK = 'grok'
    PROVIDER_ANTHROPIC = 'anthropic'
    PROVIDER_CUSTOM = 'custom'
    PROVIDER_CHOICES = [
        (PROVIDER_DEEPSEEK, 'DeepSeek'),
        (PROVIDER_OPENAI, 'OpenAI / ChatGPT'),
        (PROVIDER_GEMINI, 'Google Gemini'),
        (PROVIDER_GROK, 'xAI Grok'),
        (PROVIDER_ANTHROPIC, 'Anthropic Claude'),
        (PROVIDER_CUSTOM, 'Custom Provider'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='ai_providers',
        null=True, blank=True
    )
    is_system = models.BooleanField(default=False, help_text='Global system provider available to everyone')
    name = models.CharField(max_length=100, help_text='Friendly display name')
    provider_type = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_DEEPSEEK)
    api_base_url = models.URLField(
        max_length=500,
        help_text='Base URL for the AI API (e.g., https://api.openai.com/v1)'
    )
    api_key = models.CharField(max_length=500, help_text='API key for authentication')
    model_name = models.CharField(
        max_length=100, default='',
        help_text='Model to use (e.g., gpt-4o, gemini-pro, deepseek-chat)'
    )
    output_webhook_url = models.URLField(
        max_length=500, blank=True, default='',
        help_text='Optional webhook URL to receive responses'
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text='Default provider for requests')
    max_tokens = models.IntegerField(default=4096)
    temperature = models.FloatField(default=0.7)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Usage tracking
    total_requests = models.IntegerField(default=0)
    total_tokens_used = models.IntegerField(default=0)
    total_data_bytes = models.BigIntegerField(default=0)

    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name = 'AI Provider'

    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()})"

    @property
    def masked_api_key(self):
        if len(self.api_key) > 12:
            return f"{self.api_key[:8]}...{self.api_key[-4:]}"
        return '****'

    def increment_usage(self, tokens=0, data_bytes=0):
        self.total_requests += 1
        self.total_tokens_used += tokens
        self.total_data_bytes += data_bytes
        self.save(update_fields=['total_requests', 'total_tokens_used', 'total_data_bytes'])


class CompressionRule(models.Model):
    """
    Compression rules — system built-in or custom.
    Built-in rules are pre-defined for languages and programming (NEX).
    """
    TYPE_BUILTIN_LANGUAGE = 'builtin_language'
    TYPE_BUILTIN_PROGRAMMING = 'builtin_programming'
    TYPE_CUSTOM = 'custom'
    TYPE_CHOICES = [
        (TYPE_BUILTIN_LANGUAGE, 'Built-in Language'),
        (TYPE_BUILTIN_PROGRAMMING, 'Built-in Programming (NEX)'),
        (TYPE_CUSTOM, 'Custom'),
    ]

    LANG_DE = 'de'
    LANG_EN = 'en'
    LANG_FR = 'fr'
    LANG_ES = 'es'
    LANGUAGE_CHOICES = [
        (LANG_DE, 'German'),
        (LANG_EN, 'English'),
        (LANG_FR, 'French'),
        (LANG_ES, 'Spanish'),
    ]

    PROG_PYTHON = 'python'
    PROG_JAVASCRIPT = 'javascript'
    PROG_JAVA = 'java'
    PROG_CSHARP = 'csharp'
    PROG_SQL = 'sql'
    PROG_CHOICES = [
        (PROG_PYTHON, 'Python'),
        (PROG_JAVASCRIPT, 'JavaScript'),
        (PROG_JAVA, 'Java'),
        (PROG_CSHARP, 'C#'),
        (PROG_SQL, 'SQL'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE,
        related_name='compression_rules', null=True, blank=True,
    )
    rule_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_CUSTOM)
    is_system = models.BooleanField(default=False, help_text='System rule (cannot be deleted)')
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, blank=True, default='')
    programming_language = models.CharField(max_length=20, choices=PROG_CHOICES, blank=True, default='')
    pattern = models.CharField(
        max_length=500,
        help_text='The verbose text pattern to match'
    )
    replacement = models.CharField(
        max_length=200,
        help_text='The compressed replacement'
    )
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['rule_type', '-created_at']

    def __str__(self):
        return f'[{self.get_rule_type_display()}] "{self.pattern}" → "{self.replacement}"'


class PIIConfig(models.Model):
    """
    GDPR/PII masking configuration for an organization.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        'accounts.Organization', on_delete=models.CASCADE, related_name='pii_config'
    )
    mask_names = models.BooleanField(default=True, help_text='Mask personal names')
    mask_emails = models.BooleanField(default=True, help_text='Mask email addresses')
    mask_ibans = models.BooleanField(default=True, help_text='Mask IBAN numbers')
    mask_ips = models.BooleanField(default=True, help_text='Mask IP addresses')
    mask_phone_numbers = models.BooleanField(default=True, help_text='Mask phone numbers')
    mask_custom_ids = models.BooleanField(
        default=False,
        help_text='Mask internal document/order IDs detected by AI'
    )
    ai_detection_enabled = models.BooleanField(
        default=False,
        help_text='Use AI pre-scan to detect PII beyond regex (names, internal IDs, etc.)'
    )
    custom_regex_patterns = models.TextField(
        blank=True,
        help_text='Custom regex patterns for masking, one per line. Format: pattern|||replacement'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'PII Configuration'
        verbose_name_plural = 'PII Configurations'

    def __str__(self):
        return f"PII Config for {self.organization.name}"


class Directory(models.Model):
    """
    A user-created folder/directory to organize file analysis uploads.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='directories'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='directories'
    )
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name


class FileAnalysis(models.Model):
    """
    File uploaded for AI analysis.
    """
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_DONE = 'done'
    STATUS_ERROR = 'error'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_DONE, 'Done'),
        (STATUS_ERROR, 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='file_analyses'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='file_analyses'
    )
    directory = models.ForeignKey(
        Directory, on_delete=models.SET_NULL, null=True, blank=True, related_name='files'
    )
    ai_provider = models.ForeignKey(
        AIProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='file_analyses'
    )
    file = models.FileField(upload_to='analysis_files/%Y/%m/')
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(default=0)
    file_size = models.BigIntegerField(default=0)
    prompt = models.TextField(
        blank=True, default='Analyze the content of this file and provide a summary.',
        help_text='Instructions for the AI when analyzing this file'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    result = models.TextField(blank=True, help_text='AI analysis result')
    error_message = models.TextField(blank=True)
    tokens_used = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    processing_time_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'File Analysis'
        verbose_name_plural = 'File Analyses'

    def __str__(self):
        return f"{self.filename} ({self.get_status_display()})"


class ChatSession(models.Model):
    """
    A single chat thread in the Secure Data Chat.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='chat_sessions'
    )
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='chat_sessions'
    )
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    """
    A single message within a ChatSession.
    """
    ROLE_USER = 'user'
    ROLE_AI = 'ai'
    ROLE_CHOICES = [
        (ROLE_USER, 'User'),
        (ROLE_AI, 'AI'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.get_role_display()}] {self.content[:50]}..."


class AuditLog(models.Model):
    """
    Complete audit trail of every API interaction (Gateway, Secure Chat, File Chat).
    """
    SOURCE_GATEWAY = 'gateway'
    SOURCE_SECURE_CHAT = 'secure_chat'
    SOURCE_FILE_CHAT = 'file_chat'
    SOURCE_CHOICES = [
        (SOURCE_GATEWAY, 'API Gateway'),
        (SOURCE_SECURE_CHAT, 'Secure Chat'),
        (SOURCE_FILE_CHAT, 'File Chat'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='audit_logs'
    )
    user = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs',
        help_text='User who initiated the request (if via dashboard UI)'
    )
    api_key = models.ForeignKey(
        APIKey, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs'
    )
    ai_provider = models.ForeignKey(
        AIProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs'
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_GATEWAY)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Payload data
    original_payload = models.TextField(help_text='The original incoming JSON payload')
    compressed_payload = models.TextField(help_text='The compressed/transpiled payload')
    deepseek_response = models.TextField(help_text='Raw response from AI provider')
    final_response = models.TextField(help_text='Final formatted response sent back')

    # Metrics
    tokens_original = models.IntegerField(default=0)
    tokens_compressed = models.IntegerField(default=0)
    tokens_response = models.IntegerField(default=0)
    tokens_translated = models.IntegerField(default=0, help_text="Tokens in the final Stage 3 translation")
    compression_ratio = models.FloatField(default=0.0)
    cost_original = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    cost_actual = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    cost_saved = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.IntegerField(default=0)
    cache_hit = models.BooleanField(default=False)
    data_bytes_in = models.BigIntegerField(default=0)
    data_bytes_out = models.BigIntegerField(default=0)

    # Status
    STATUS_SUCCESS = 'success'
    STATUS_ERROR = 'error'
    STATUS_CACHED = 'cached'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_ERROR, 'Error'),
        (STATUS_CACHED, 'Cached'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def __str__(self):
        return f"[{self.status}] {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

    @property
    def input_tokens_saved(self):
        return self.tokens_original - self.tokens_compressed

    @property
    def input_savings_percentage(self):
        if self.tokens_original == 0:
            return 0
        return round((self.input_tokens_saved / self.tokens_original) * 100, 1)

    @property
    def output_tokens_saved(self):
        # Human text - NEX text
        return self.tokens_translated - self.tokens_response

    @property
    def output_savings_percentage(self):
        if self.tokens_translated == 0:
            return 0
        return round((self.output_tokens_saved / self.tokens_translated) * 100, 1)


class MaskedDocument(models.Model):
    """
    A document where sensitive data has been replaced with placeholders.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='masked_documents'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='masked_documents'
    )
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField(default=0)
    clean_content = models.TextField(help_text='The text of the document with placeholders inserted')
    redacted_file = models.FileField(upload_to='masked_docs/%Y/%m/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Masked Document'
        verbose_name_plural = 'Masked Documents'

    def __str__(self):
        return self.filename


class DocumentKeyMapping(models.Model):
    """
    Maps a placeholder in a MaskedDocument back to its original value.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        MaskedDocument, on_delete=models.CASCADE, related_name='key_mappings'
    )
    placeholder = models.CharField(max_length=50, help_text='e.g., [EMAIL_1]')
    original_value = models.CharField(max_length=500)
    pii_type = models.CharField(max_length=50)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.placeholder} -> {self.original_value}"
