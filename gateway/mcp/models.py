"""
Firma-KI Gateway — MCP Models
Tool registry, permission matrix, and audit logging for AI agent tool execution.
"""
import uuid
from django.db import models


class MCPTool(models.Model):
    """
    Registry of tools available through the MCP Gateway.
    Each tool represents an action an AI agent can request (SQL query,
    script execution, API call, file access).
    """
    TOOL_SQL_QUERY = 'sql_query'
    TOOL_SCRIPT_EXEC = 'script_exec'
    TOOL_API_CALL = 'api_call'
    TOOL_FILE_ACCESS = 'file_access'
    TOOL_CUSTOM = 'custom'
    TOOL_TYPE_CHOICES = [
        (TOOL_SQL_QUERY, 'SQL Query'),
        (TOOL_SCRIPT_EXEC, 'Script Execution'),
        (TOOL_API_CALL, 'API Call'),
        (TOOL_FILE_ACCESS, 'File Access'),
        (TOOL_CUSTOM, 'Custom Tool'),
    ]

    RISK_LOW = 'low'
    RISK_MEDIUM = 'medium'
    RISK_HIGH = 'high'
    RISK_CRITICAL = 'critical'
    RISK_LEVEL_CHOICES = [
        (RISK_LOW, 'Low'),
        (RISK_MEDIUM, 'Medium'),
        (RISK_HIGH, 'High'),
        (RISK_CRITICAL, 'Critical'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='mcp_tools'
    )
    name = models.CharField(max_length=100, help_text='Unique tool identifier')
    display_name = models.CharField(max_length=200, help_text='Human-readable tool name')
    description = models.TextField(blank=True, help_text='What this tool does')
    tool_type = models.CharField(max_length=20, choices=TOOL_TYPE_CHOICES, default=TOOL_CUSTOM)
    risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default=RISK_MEDIUM)
    
    # Tool configuration
    endpoint_url = models.URLField(max_length=500, blank=True, help_text='Target endpoint for API call tools')
    allowed_params = models.JSONField(
        default=dict, blank=True,
        help_text='JSON schema of allowed parameters for this tool'
    )
    blocked_patterns = models.TextField(
        blank=True, default='',
        help_text='Regex patterns to block in tool inputs (one per line). E.g., DROP TABLE, DELETE FROM'
    )
    max_execution_time_ms = models.IntegerField(
        default=30000, help_text='Max execution time before timeout (ms)'
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('organization', 'name')
        ordering = ['name']
        verbose_name = 'MCP Tool'
        verbose_name_plural = 'MCP Tools'

    def __str__(self):
        return f"{self.display_name} ({self.tool_type})"


class MCPPermission(models.Model):
    """
    Permission matrix: which API key / AI provider can execute which tools.
    Gives IT administrators granular control over tool access.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='mcp_permissions'
    )
    tool = models.ForeignKey(MCPTool, on_delete=models.CASCADE, related_name='permissions')
    api_key = models.ForeignKey(
        'dashboard.APIKey', on_delete=models.CASCADE,
        null=True, blank=True, related_name='mcp_permissions',
        help_text='Specific API key granted this permission (null = all keys)'
    )
    ai_provider = models.ForeignKey(
        'dashboard.AIProvider', on_delete=models.CASCADE,
        null=True, blank=True, related_name='mcp_permissions',
        help_text='Specific AI provider granted this permission (null = all providers)'
    )
    
    is_allowed = models.BooleanField(default=True, help_text='Allow or deny access')
    max_calls_per_minute = models.IntegerField(
        default=10, help_text='Rate limit for this tool-key combination'
    )
    requires_human_approval = models.BooleanField(
        default=False, help_text='Require human approval before execution'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'MCP Permission'
        verbose_name_plural = 'MCP Permissions'

    def __str__(self):
        key_str = str(self.api_key) if self.api_key else 'ALL'
        return f"{key_str} → {self.tool.name} ({'✓' if self.is_allowed else '✗'})"


class MCPAuditLog(models.Model):
    """
    Every MCP tool execution is logged for compliance and debugging.
    """
    STATUS_SUCCESS = 'success'
    STATUS_DENIED = 'denied'
    STATUS_ERROR = 'error'
    STATUS_TIMEOUT = 'timeout'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_DENIED, 'Permission Denied'),
        (STATUS_ERROR, 'Error'),
        (STATUS_TIMEOUT, 'Timeout'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'accounts.Organization', on_delete=models.CASCADE, related_name='mcp_audit_logs'
    )
    tool = models.ForeignKey(
        MCPTool, on_delete=models.SET_NULL, null=True, related_name='audit_logs'
    )
    api_key = models.ForeignKey(
        'dashboard.APIKey', on_delete=models.SET_NULL, null=True, related_name='mcp_audit_logs'
    )
    
    tool_name = models.CharField(max_length=100)
    input_params = models.JSONField(default=dict, help_text='Sanitized input parameters')
    output_result = models.TextField(blank=True, help_text='Tool execution result')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    error_message = models.TextField(blank=True)
    execution_time_ms = models.IntegerField(default=0)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'MCP Audit Log'
        verbose_name_plural = 'MCP Audit Logs'

    def __str__(self):
        return f"[{self.status}] {self.tool_name} @ {self.timestamp}"
