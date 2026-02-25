"""
Firma-KI Gateway — Deterministic Decoder
Post-processes DeepSeek responses: re-injects PII, validates JSON, formats output.
"""
import json
import re


class DeterministicDecoder:
    """
    Ensures DeepSeek output is deterministic, properly formatted,
    and has PII re-injected.
    """

    def __init__(self, pii_masker=None):
        self.pii_masker = pii_masker

    def decode(self, response_content, mask_map=None):
        """
        Post-process the DeepSeek response.
        1. Re-inject masked PII values
        2. Validate/fix JSON if applicable
        3. Clean formatting
        """
        result = response_content

        # Re-inject PII
        if self.pii_masker and mask_map:
            result = self.pii_masker.unmask(result, mask_map)

        # Try to parse and re-format JSON responses
        result = self._try_format_json(result)

        return result

    def _try_format_json(self, text):
        """
        If the response looks like JSON, parse and re-format it
        for deterministic output.
        """
        stripped = text.strip()

        # Check if it looks like JSON
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                parsed = json.loads(stripped)
                return json.dumps(parsed, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', stripped)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(1).strip())
                        return json.dumps(parsed, indent=2, ensure_ascii=False)
                    except json.JSONDecodeError:
                        pass

        return text

    def format_openai_response(self, deepseek_data, original_id=None):
        """
        Format response in OpenAI-compatible structure.
        """
        return {
            'id': original_id or deepseek_data.get('id', 'chatcmpl-firmaki'),
            'object': 'chat.completion',
            'model': deepseek_data.get('model', 'deepseek-chat'),
            'choices': [{
                'index': 0,
                'message': {
                    'role': deepseek_data.get('role', 'assistant'),
                    'content': deepseek_data.get('content', ''),
                },
                'finish_reason': deepseek_data.get('finish_reason', 'stop'),
            }],
            'usage': deepseek_data.get('usage', {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0,
            }),
            'firma_ki': {
                'compressed': True,
                'gateway': 'firma-ki.de',
            }
        }
