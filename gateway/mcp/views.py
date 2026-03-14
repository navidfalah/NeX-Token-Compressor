"""
Firma-KI Gateway — MCP Views
HTTP endpoint for AI agent tool execution through the MCP Gateway.
"""
import json

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from gateway.authentication import authenticate_api_key, APIKeyAuthenticationError
from .executor import MCPExecutor


@method_decorator(csrf_exempt, name='dispatch')
class MCPExecuteView(View):
    """
    POST /v1/mcp/execute
    
    Authenticated endpoint for AI agent tool execution.
    
    Request body:
    {
        "tool": "tool_name",
        "params": { ... }
    }
    
    Response:
    {
        "status": "success" | "denied" | "error",
        "tool": "tool_name",
        "output": { ... },
        "metadata": { ... }
    }
    """

    def post(self, request, *args, **kwargs):
        # Authenticate
        try:
            api_key, organization = authenticate_api_key(request)
        except APIKeyAuthenticationError as e:
            return JsonResponse({'error': str(e)}, status=401)

        # Parse request
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)

        tool_name = body.get('tool', '')
        params = body.get('params', {})

        if not tool_name:
            return JsonResponse({'error': 'Missing "tool" field.'}, status=400)

        # Execute through MCP
        result = MCPExecutor.execute(tool_name, params, api_key, organization)

        # Map status to HTTP status code
        status_map = {
            'success': 200,
            'denied': 403,
            'error': 500,
        }
        http_status = status_map.get(result.get('status', 'error'), 500)

        return JsonResponse(result, status=http_status)

    def get(self, request, *args, **kwargs):
        """
        GET /v1/mcp/execute — List available tools.
        """
        try:
            api_key, organization = authenticate_api_key(request)
        except APIKeyAuthenticationError as e:
            return JsonResponse({'error': str(e)}, status=401)

        tools = MCPExecutor.list_tools(organization, api_key)
        return JsonResponse({'tools': tools})
