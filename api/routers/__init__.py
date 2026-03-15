from fastapi import APIRouter
from . import gateway
from . import dashboard
from . import accounts

__all__ = ["gateway", "dashboard", "accounts"]
