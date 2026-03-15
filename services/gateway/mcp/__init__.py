"""
Firma-KI Gateway — Centralized MCP (Model Context Protocol) Gateway
Secure intermediary for AI agent tool execution.
"""
from .firewall import MCPFirewall
from .executor import MCPExecutor

__all__ = ['MCPFirewall', 'MCPExecutor']
