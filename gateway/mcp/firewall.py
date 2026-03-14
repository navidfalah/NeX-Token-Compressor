"""
Firma-KI Gateway — MCP Firewall
Centralized security layer for AI agent tool execution.
Validates permissions, sanitizes inputs, and prevents dangerous operations.
"""
import re
import time


class MCPFirewallError(Exception):
    """Raised when a firewall check fails."""
    pass


class MCPFirewall:
    """
    Unified Agent Firewall.
    
    When a client's AI agent attempts to access an internal SQL database
    or execute a script, it must pass through this firewall. Provides:
    
    1. Permission checking (is this API key allowed to use this tool?)
    2. Input sanitization (SQL injection prevention, path traversal blocking)
    3. Rate limiting
    4. Dangerous pattern blocking
    """

    # Universal dangerous patterns (always blocked regardless of tool config)
    UNIVERSAL_BLOCKED_PATTERNS = [
        # SQL injection
        r';\s*DROP\s+', r';\s*DELETE\s+FROM\s+', r';\s*TRUNCATE\s+',
        r';\s*ALTER\s+', r';\s*CREATE\s+', r'UNION\s+SELECT',
        r'--\s*$',  # SQL comment injection
        # Path traversal
        r'\.\./|\.\.\\', r'/etc/passwd', r'/etc/shadow',
        r'%2e%2e', r'%252e%252e',
        # Command injection
        r';\s*(?:rm|sudo|chmod|chown|kill|shutdown|reboot)\s',
        r'\$\(', r'`[^`]*`',  # Command substitution
        r'\|\s*(?:bash|sh|zsh|cmd|powershell)',
        # Script injection
        r'<script[^>]*>', r'javascript:', r'eval\s*\(',
    ]

    @classmethod
    def check_permission(cls, api_key, tool, organization) -> dict:
        """
        Check if an API key has permission to execute a tool.
        
        Returns:
            Permission details dict with 'allowed' boolean.
            
        Raises:
            MCPFirewallError if access is denied.
        """
        from .models import MCPPermission

        # Check for explicit permission entry
        permission = MCPPermission.objects.filter(
            organization=organization,
            tool=tool,
        ).filter(
            # Match specific key OR wildcard (null key = all keys)
            models_api_key_filter(api_key)
        ).first()

        if permission is None:
            # No permission record = denied by default (secure by default)
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
        """
        Sanitize tool input parameters against dangerous patterns.
        
        Args:
            tool: MCPTool instance
            params: Raw input parameters from the AI agent
            
        Returns:
            Sanitized parameters dict.
            
        Raises:
            MCPFirewallError if dangerous patterns are detected.
        """
        sanitized = {}
        
        for key, value in params.items():
            if isinstance(value, str):
                # Check universal blocked patterns
                cls._check_blocked_patterns(
                    value, cls.UNIVERSAL_BLOCKED_PATTERNS,
                    f"Universal security violation in param '{key}'"
                )
                
                # Check tool-specific blocked patterns
                if tool.blocked_patterns:
                    tool_patterns = [
                        p.strip() for p in tool.blocked_patterns.strip().split('\n')
                        if p.strip()
                    ]
                    cls._check_blocked_patterns(
                        value, tool_patterns,
                        f"Tool policy violation in param '{key}'"
                    )
                
                # Sanitize the value
                sanitized[key] = cls._sanitize_string(value)
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
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
        """Check a string value against a list of blocked regex patterns."""
        for pattern in patterns:
            try:
                if re.search(pattern, value, re.IGNORECASE):
                    raise MCPFirewallError(
                        f"{error_prefix}: blocked pattern detected — '{pattern}'"
                    )
            except re.error:
                continue  # Skip invalid patterns

    @classmethod
    def _sanitize_string(cls, value: str) -> str:
        """
        Apply basic sanitization to string inputs.
        Removes null bytes and excessive whitespace.
        """
        # Remove null bytes
        sanitized = value.replace('\x00', '')
        # Normalize whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        return sanitized

    @classmethod
    def validate_tool_exists(cls, tool_name: str, organization) -> 'MCPTool':
        """
        Validate that a tool exists and is active.
        
        Returns:
            MCPTool instance.
            
        Raises:
            MCPFirewallError if tool not found or inactive.
        """
        from .models import MCPTool

        try:
            tool = MCPTool.objects.get(
                organization=organization,
                name=tool_name,
                is_active=True,
            )
            return tool
        except MCPTool.DoesNotExist:
            raise MCPFirewallError(
                f"Tool '{tool_name}' not found or is inactive."
            )


def models_api_key_filter(api_key):
    """Build a Q filter for matching specific key or wildcard permissions."""
    from django.db.models import Q
    return Q(api_key=api_key) | Q(api_key__isnull=True)
