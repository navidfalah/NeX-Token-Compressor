from datetime import datetime
import uuid

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean, Float
from sqlalchemy.orm import relationship

from . import Base

class CacheEntry(Base):
    __tablename__ = "gateway_cacheentry"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    prompt_hash = Column(String(64), nullable=False)
    response_json = Column(Text, nullable=False)
    tokens_used = Column(Integer, nullable=False, default=0)
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_hit_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False)


class MCPTool(Base):
    __tablename__ = "gateway_mcptool"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False, default="")
    risk_level = Column(String(20), nullable=False, default="medium")
    blocked_patterns = Column(Text, nullable=False, default="")
    is_active = Column(Boolean, nullable=False, default=True)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False)


class MCPPermission(Base):
    __tablename__ = "gateway_mcppermission"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    tool_id = Column(String(32), ForeignKey("gateway_mcptool.id"), nullable=False)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False)
    api_key_id = Column(String(32), ForeignKey("dashboard_apikey.id"), nullable=True)
    
    is_allowed = Column(Boolean, nullable=False, default=True)
    requires_human_approval = Column(Boolean, nullable=False, default=False)
    max_calls_per_minute = Column(Integer, nullable=False, default=60)


class EdgeNode(Base):
    __tablename__ = "gateway_edgenode"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String(100), nullable=False)
    region = Column(String(50), nullable=False)
    location = Column(String(100), nullable=False)
    ip_address = Column(String(45), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    data_sovereignty_zone = Column(String(20), nullable=False, default="eu")
    current_load_pct = Column(Float, nullable=False, default=0.0)


class EdgeRoutingRule(Base):
    __tablename__ = "gateway_edgeroutingrule"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    source_region = Column(String(50), nullable=False)
    target_node_id = Column(String(32), ForeignKey("gateway_edgenode.id"), nullable=False)
    priority = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=True)
