"""
Firma-KI Gateway — MCP Executor
Executes validated tool requests through the MCP Gateway.
All executions pass through the firewall first.
"""
import json
import time

from .firewall import MCPFirewall, MCPFirewallError
from models.gateway import MCPTool, MCPAuditLog


class MCPExecutor:
    """
    Centralized MCP tool executor.
    
    Processes tool execution requests from AI agents:
    1. Validates the tool exists and is active
    2. Checks permissions through the firewall
    3. Sanitizes input parameters
    4. Executes the tool (delegates to type-specific handlers)
    5. Logs the execution
    """

    @classmethod
    def execute(cls, tool_name: str, params: dict, api_key, organization) -> dict:
        """
        Execute a tool through the MCP Gateway.
        
        Args:
            tool_name: Name of the registered tool to execute
            params: Input parameters for the tool
            api_key: The authenticated API key making the request
            organization: The organization context
            
        Returns:
            Execution result dict with status, output, and metadata.
        """
        start_time = time.time()
        
        try:
            # Step 1: Validate tool exists
            tool = MCPFirewall.validate_tool_exists(tool_name, organization)

            # Step 2: Check permissions
            permission_info = MCPFirewall.check_permission(api_key, tool, organization)

            # Step 3: Sanitize inputs
            sanitized_params = MCPFirewall.sanitize_input(tool, params)

            # Step 4: Execute
            result = cls._dispatch_execution(tool, sanitized_params)
            execution_time = int((time.time() - start_time) * 1000)

            # Step 5: Log success
            MCPAuditLog.objects.create(
                organization=organization,
                tool=tool,
                api_key=api_key,
                tool_name=tool_name,
                input_params=sanitized_params,
                output_result=json.dumps(result.get('output', ''), default=str)[:5000],
                status=MCPAuditLog.STATUS_SUCCESS,
                execution_time_ms=execution_time,
            )

            return {
                'status': 'success',
                'tool': tool_name,
                'output': result.get('output', ''),
                'metadata': {
                    'execution_time_ms': execution_time,
                    'risk_level': tool.risk_level,
                    'tool_type': tool.tool_type,
                },
            }

        except MCPFirewallError as e:
            execution_time = int((time.time() - start_time) * 1000)
            
            # Log denied attempt
            try:
                MCPAuditLog.objects.create(
                    organization=organization,
                    api_key=api_key,
                    tool_name=tool_name,
                    input_params=params,
                    status=MCPAuditLog.STATUS_DENIED,
                    error_message=str(e),
                    execution_time_ms=execution_time,
                )
            except Exception:
                pass  # Don't fail on audit log errors

            return {
                'status': 'denied',
                'tool': tool_name,
                'error': str(e),
                'metadata': {
                    'execution_time_ms': execution_time,
                },
            }

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            
            # Log error
            try:
                MCPAuditLog.objects.create(
                    organization=organization,
                    api_key=api_key,
                    tool_name=tool_name,
                    input_params=params,
                    status=MCPAuditLog.STATUS_ERROR,
                    error_message=str(e),
                    execution_time_ms=execution_time,
                )
            except Exception:
                pass

            return {
                'status': 'error',
                'tool': tool_name,
                'error': f'Execution failed: {str(e)}',
                'metadata': {
                    'execution_time_ms': execution_time,
                },
            }

    @classmethod
    def _dispatch_execution(cls, tool: MCPTool, params: dict) -> dict:
        """
        Dispatch to the appropriate executor based on tool type.
        
        This is the extension point for adding new tool type handlers.
        """
        handlers = {
            MCPTool.TOOL_SQL_QUERY: cls._execute_sql_query,
            MCPTool.TOOL_SCRIPT_EXEC: cls._execute_script,
            MCPTool.TOOL_API_CALL: cls._execute_api_call,
            MCPTool.TOOL_FILE_ACCESS: cls._execute_file_access,
            MCPTool.TOOL_CUSTOM: cls._execute_custom,
        }

        handler = handlers.get(tool.tool_type, cls._execute_custom)
        return handler(tool, params)

    @classmethod
    def _execute_sql_query(cls, tool: MCPTool, params: dict) -> dict:
        """
        Execute a SQL query tool.
        Currently returns a structured placeholder — actual DB execution
        requires explicit configuration of allowed databases.
        """
        query = params.get('query', '')
        return {
            'output': {
                'tool_type': 'sql_query',
                'query_received': query,
                'note': 'SQL execution requires database configuration. '
                        'Configure the database endpoint in tool settings.',
                'status': 'pending_configuration'
            }
        }

    @classmethod
    def _execute_script(cls, tool: MCPTool, params: dict) -> dict:
        """
        Execute a script tool.
        Sandboxed execution — requires explicit environment configuration.
        """
        script = params.get('script', '')
        language = params.get('language', 'python')
        return {
            'output': {
                'tool_type': 'script_exec',
                'script_length': len(script),
                'language': language,
                'note': 'Script execution requires sandbox configuration. '
                        'Configure the execution environment in tool settings.',
                'status': 'pending_configuration'
            }
        }

    @classmethod
    def _execute_api_call(cls, tool: MCPTool, params: dict) -> dict:
        """
        Execute an API call tool.
        Makes an HTTP request to the configured endpoint.
        """
        import urllib.request
        import urllib.error

        if not tool.endpoint_url:
            return {
                'output': {
                    'error': 'No endpoint URL configured for this tool.',
                    'status': 'configuration_error'
                }
            }

        method = params.get('method', 'GET').upper()
        headers = params.get('headers', {})
        body = params.get('body', None)

        try:
            req = urllib.request.Request(
                tool.endpoint_url,
                data=json.dumps(body).encode('utf-8') if body else None,
                headers={'Content-Type': 'application/json', **headers},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=tool.max_execution_time_ms / 1000) as resp:
                response_body = resp.read().decode('utf-8')
                return {
                    'output': {
                        'status_code': resp.status,
                        'body': response_body[:5000],  # Truncate large responses
                    }
                }
        except urllib.error.HTTPError as e:
            return {
                'output': {
                    'error': f'HTTP {e.code}',
                    'body': e.read().decode('utf-8', errors='replace')[:2000],
                }
            }
        except Exception as e:
            return {'output': {'error': str(e)}}

    @classmethod
    def _execute_file_access(cls, tool: MCPTool, params: dict) -> dict:
        """
        Execute a file access tool.
        Read-only access with strict path validation.
        """
        return {
            'output': {
                'tool_type': 'file_access',
                'note': 'File access requires explicit directory whitelist configuration. '
                        'Configure allowed paths in tool settings.',
                'status': 'pending_configuration'
            }
        }

    @classmethod
    def _execute_custom(cls, tool: MCPTool, params: dict) -> dict:
        """
        Execute a custom tool.
        Delegates to the tool's endpoint_url if configured.
        """
        if tool.endpoint_url:
            return cls._execute_api_call(tool, params)
        
        return {
            'output': {
                'tool_type': 'custom',
                'params_received': params,
                'note': 'Custom tool executed. Configure endpoint_url for external execution.',
                'status': 'acknowledged'
            }
        }

    @classmethod
    def list_tools(cls, organization, api_key=None) -> list[dict]:
        """
        List all available tools for an organization, filtered by permissions.
        """
        tools = MCPTool.objects.filter(
            organization=organization,
            is_active=True,
        )

        tool_list = []
        for tool in tools:
            # Check if API key has permission
            try:
                MCPFirewall.check_permission(api_key, tool, organization)
                accessible = True
            except MCPFirewallError:
                accessible = False

            tool_list.append({
                'name': tool.name,
                'display_name': tool.display_name,
                'description': tool.description,
                'type': tool.tool_type,
                'risk_level': tool.risk_level,
                'accessible': accessible,
            })

        return tool_list
