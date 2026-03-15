from datetime import datetime
import uuid
import secrets

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, BigInteger, Float, Numeric, Text
from sqlalchemy.orm import relationship

from . import Base

class AIProvider(Base):
    __tablename__ = "dashboard_aiprovider"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String(100), nullable=False)
    provider_type = Column(String(20), nullable=False, default="deepseek")
    api_base_url = Column(String(500), nullable=False)
    api_key = Column(String(500), nullable=False)
    model_name = Column(String(100), nullable=False)
    output_webhook_url = Column(String(500), nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    max_tokens = Column(Integer, nullable=False, default=4096)
    temperature = Column(Float, nullable=False, default=0.7)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_requests = Column(Integer, nullable=False, default=0)
    total_tokens_used = Column(Integer, nullable=False, default=0)
    total_data_bytes = Column(BigInteger, nullable=False, default=0)
    is_system = Column(Boolean, nullable=False, default=False)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=True)

    @property
    def masked_api_key(self):
        if self.api_key:
            return f"{self.api_key[:6]}...{self.api_key[-4:]}" if len(self.api_key) > 10 else self.api_key
        return "N/A"


class APIKey(Base):
    __tablename__ = "dashboard_apikey"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String(100), nullable=False)
    key = Column(String(64), nullable=False, unique=True, default=lambda: f"fk-{secrets.token_hex(28)}")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False)
    user_id = Column(String(32), ForeignKey("accounts_user.id"), nullable=False)
    
    allowed_models = Column(String(500), nullable=False, default="")
    daily_token_limit = Column(Integer, nullable=False, default=0)
    enable_caching = Column(Boolean, nullable=False, default=True)
    enable_compression = Column(Boolean, nullable=False, default=True)
    linked_provider_id = Column(String(32), ForeignKey("dashboard_aiprovider.id"), nullable=True)
    rate_limit = Column(Integer, nullable=False, default=60)

    @property
    def masked_key(self):
        if self.key:
            return f"{self.key[:6]}...{self.key[-4:]}" if len(self.key) > 10 else self.key
        return "N/A"

    organization = relationship("Organization", back_populates="api_keys")


class CompressionRule(Base):
    __tablename__ = "dashboard_compressionrule"
    
    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    rule_type = Column(String(30), nullable=False)
    is_system = Column(Boolean, nullable=False, default=False)
    language = Column(String(5), nullable=False, default="")
    programming_language = Column(String(20), nullable=False, default="")
    pattern = Column(String(500), nullable=False)
    replacement = Column(String(200), nullable=False)
    description = Column(String(300), nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=True)

class AuditLog(Base):
    __tablename__ = "dashboard_auditlog"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    original_payload = Column(Text, nullable=False)
    compressed_payload = Column(Text, nullable=False)
    deepseek_response = Column(Text, nullable=False)
    final_response = Column(Text, nullable=False)
    tokens_original = Column(Integer, nullable=False, default=0)
    tokens_compressed = Column(Integer, nullable=False, default=0)
    tokens_response = Column(Integer, nullable=False, default=0)
    tokens_translated = Column(Integer, nullable=False, default=0)
    compression_ratio = Column(Float, nullable=False, default=0.0)
    cost_original = Column(Numeric(10, 6), nullable=False, default=0)
    cost_actual = Column(Numeric(10, 6), nullable=False, default=0)
    cost_saved = Column(Numeric(10, 6), nullable=False, default=0)
    latency_ms = Column(Integer, nullable=False, default=0)
    cache_hit = Column(Boolean, nullable=False, default=False)
    data_bytes_in = Column(BigInteger, nullable=False, default=0)
    data_bytes_out = Column(BigInteger, nullable=False, default=0)
    status = Column(String(10), nullable=False, default="success")
    error_message = Column(Text, nullable=False, default="")
    source = Column(String(20), nullable=False, default="gateway")
    
    ai_provider_id = Column(String(32), ForeignKey("dashboard_aiprovider.id"), nullable=True)
    api_key_id = Column(String(32), ForeignKey("dashboard_apikey.id"), nullable=True)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False)
    user_id = Column(String(32), ForeignKey("accounts_user.id"), nullable=True)

    ai_provider = relationship("AIProvider")
    api_key = relationship("APIKey")
    organization = relationship("Organization")
    @property
    def source_label(self):
        return self.source.capitalize()

    @property
    def api_key_masked(self):
        if self.api_key:
            return f"{self.api_key.key[:6]}...{self.api_key.key[-4:]}"
        return "N/A"

    @property
    def stripped_tags(self):
        # Logic to extract redacted entities could go here
        return []


class CascadeConfig(Base):
    __tablename__ = "dashboard_cascadeconfig"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    confidence_threshold = Column(Float, nullable=False, default=0.7)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    cheap_provider_id = Column(String(32), ForeignKey("dashboard_aiprovider.id"), nullable=True)
    heavyweight_provider_id = Column(String(32), ForeignKey("dashboard_aiprovider.id"), nullable=True)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False, unique=True)


class SecureDocument(Base):
    __tablename__ = "dashboard_securedocument"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    filename = Column(String(255), nullable=False)
    original_file = Column(String(500), nullable=False) # Path to file
    redacted_file = Column(String(500), nullable=True)  # Path to redacted file
    file_size = Column(BigInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False)
    user_id = Column(String(32), ForeignKey("accounts_user.id"), nullable=False)
    clean_content = Column(Text, nullable=False, default="")

    key_mappings = relationship("KeyMapping", back_populates="document", cascade="all, delete-orphan")

class KeyMapping(Base):
    __tablename__ = "dashboard_keymapping"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    placeholder = Column(String(100), nullable=False)
    original_value = Column(String(500), nullable=False)
    entity_type = Column(String(50), nullable=False)
    document_id = Column(String(32), ForeignKey("dashboard_securedocument.id"), nullable=False)

    document = relationship("SecureDocument", back_populates="key_mappings")

class PrivacyConfig(Base):
    __tablename__ = "dashboard_privacyconfig"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    ai_detection_enabled = Column(Boolean, default=True)
    mask_custom_ids = Column(Boolean, default=True)
    mask_names = Column(Boolean, default=True)
    mask_emails = Column(Boolean, default=True)
    mask_ibans = Column(Boolean, default=True)
    mask_ips = Column(Boolean, default=True)
    mask_phone_numbers = Column(Boolean, default=True)
    custom_regex_patterns = Column(Text, default="")
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False, unique=True)
