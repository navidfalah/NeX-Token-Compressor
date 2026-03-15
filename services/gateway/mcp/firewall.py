"""
Firma-KI Gateway — MCP Firewall
Centralized security layer for AI agent tool execution.
Validates permissions, sanitizes inputs, and prevents dangerous operations.
"""
import re
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from models.gateway import MCPTool, MCPPermission


class MCPFirewallError(Exception):
    """Raised when a firewall check fails."""
    pass


class MCPFirewall:
    """
    Unified Agent Firewall.
    """

    UNIVERSAL_BLOCKED_PATTERNS = [
        r';\s*DROP\s+', r';\s*DELETE\s+FROM\s+', r';\s*TRUNCATE\s+',
        r';\s*ALTER\s+', r';\s*CREATE\s+', r'UNION\s+SELECT',
        r'--\s*$',
        r'\.\./|\.\.\\', r'/etc/passwd', r'/etc/shadow',
        r'%2e%2e', r'%252e%252e',
        r';\s*(?:rm|sudo|chmod|chown|kill|shutdown|reboot)\s',
        r'\$\(', r'`[^`]*`',
        r'\|\s*(?:bash|sh|zsh|cmd|powershell)',
        r'<script[^>]*>', r'javascript:', r'eval\s*\(',
    ]

    @classmethod
    async def check_permission(cls, db: AsyncSession, api_key, tool: MCPTool, organization) -> dict:
        """
        Check if an API key has permission to execute a tool.
        """
        stmt = select(MCPPermission).where(
            MCPPermission.organization_id == organization.id,
            MCPPermission.tool_id == tool.id
        ).where(
            or_(
                MCPPermission.api_key_id == api_key.id,
                MCPPermission.api_key_id == None
            )
        ).limit(1)

        result = await db.execute(stmt)
        permission = result.scalar_one_or_none()

        if permission is None:
            raise MCPFirewallError(
                f"No permission configured for tool '{tool.name}'. "
                f"Contact your administrator to grant access."
            )

        if not permission.is_allowed:
            raise MCPFirewallError(
                f"Access to tool '{tool.name}' is explicitly denied for this API key."
            )

        if permission.requires_human_approval:
            raise MCPFirewallError(
                f"Tool '{tool.name}' requires human approval before execution. "
                f"Please request approval from your administrator."
            )

        return {
            'allowed': True,
            'rate_limit': permission.max_calls_per_minute,
            'tool_risk_level': tool.risk_level,
        }

    @classmethod
    def sanitize_input(cls, tool, params: dict) -> dict:
        sanitized = {}
        for key, value in params.items():
            if isinstance(value, str):
                cls._check_blocked_patterns(
                    value, cls.UNIVERSAL_BLOCKED_PATTERNS,
                    f"Universal security violation in param '{key}'"
                )
                if tool.blocked_patterns:
                    tool_patterns = [
                        p.strip() for p in tool.blocked_patterns.strip().split('\n')
                        if p.strip()
                    ]
                    cls._check_blocked_patterns(
                        value, tool_patterns,
                        f"Tool policy violation in param '{key}'"
                    )
                sanitized[key] = cls._sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = cls.sanitize_input(tool, value)
            elif isinstance(value, list):
                sanitized[key] = [
                    cls.sanitize_input(tool, {'_': item})['_']
                    if isinstance(item, (str, dict)) else item
                    for item in value
                ]
            else:
                sanitized[key] = value
        return sanitized

    @classmethod
    def _check_blocked_patterns(cls, value: str, patterns: list, error_prefix: str):
        for pattern in patterns:
            try:
                if re.search(pattern, value, re.IGNORECASE):
                    raise MCPFirewallError(
                        f"{error_prefix}: blocked pattern detected — '{pattern}'"
                    )
            except re.error:
                continue

    @classmethod
    def _sanitize_string(cls, value: str) -> str:
        sanitized = value.replace('\x00', '')
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        return sanitized

    @classmethod
    async def validate_tool_exists(cls, db: AsyncSession, tool_name: str, organization) -> MCPTool:
        stmt = select(MCPTool).where(
            MCPTool.organization_id == organization.id,
            MCPTool.name == tool_name,
            MCPTool.is_active == True
        )
        result = await db.execute(stmt)
        tool = result.scalar_one_or_none()
        if not tool:
            raise MCPFirewallError(f"Tool '{tool_name}' not found or is inactive.")
        return tool
