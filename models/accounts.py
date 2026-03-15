from datetime import datetime
import uuid

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from . import Base

class Organization(Base):
    __tablename__ = "accounts_organization"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String(200), nullable=False)
    slug = Column(String(200), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = relationship("User", back_populates="organization")
    api_keys = relationship("APIKey", back_populates="organization")
    # cascade_config = relationship("CascadeConfig", back_populates="organization", uselist=False)

class User(Base):
    __tablename__ = "accounts_user"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    password = Column(String(128), nullable=False)
    last_login = Column(DateTime, nullable=True)
    is_superuser = Column(Boolean, nullable=False, default=False)
    username = Column(String(150), nullable=False, unique=True)
    first_name = Column(String(150), nullable=False)
    last_name = Column(String(150), nullable=False)
    email = Column(String(254), nullable=False)
    is_staff = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    date_joined = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    role = Column(String(10), nullable=False, default='user')
    last_activity = Column(DateTime, nullable=True)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=True)

    organization = relationship("Organization", back_populates="members")


class Invitation(Base):
    __tablename__ = "accounts_invitation"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    email = Column(String(254), nullable=False)
    token = Column(String(32), nullable=False, unique=True, default=lambda: uuid.uuid4().hex)
    accepted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    invited_by_id = Column(String(32), ForeignKey("accounts_user.id"), nullable=False)
    organization_id = Column(String(32), ForeignKey("accounts_organization.id"), nullable=False)
