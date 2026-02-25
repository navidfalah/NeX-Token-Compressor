"""
Firma-KI Gateway — DeepSeek Client
OpenAI-compatible wrapper for the DeepSeek API.
"""
from django.conf import settings
from openai import OpenAI


class DeepSeekClient:
    """
    Wraps the DeepSeek API using the OpenAI-compatible SDK.
    """

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        self.model = settings.DEEPSEEK_MODEL

    def chat_completion(self, messages, **kwargs):
        """
        Send a chat completion request to DeepSeek.
        Returns the full response object.
        """
        params = {
            'model': kwargs.get('model', self.model),
            'messages': messages,
        }

        # Forward optional parameters
        optional_params = [
            'temperature', 'top_p', 'max_tokens', 'stream',
            'stop', 'presence_penalty', 'frequency_penalty',
            'response_format',
        ]
        for param in optional_params:
            if param in kwargs:
                params[param] = kwargs[param]

        response = self.client.chat.completions.create(**params)
        return response

    def extract_response_data(self, response):
        """
        Extract useful data from the DeepSeek response.
        Returns dict with content, usage, and metadata.
        """
        choice = response.choices[0] if response.choices else None
        return {
            'content': choice.message.content if choice else '',
            'role': choice.message.role if choice else 'assistant',
            'finish_reason': choice.finish_reason if choice else None,
            'usage': {
                'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                'completion_tokens': response.usage.completion_tokens if response.usage else 0,
                'total_tokens': response.usage.total_tokens if response.usage else 0,
            },
            'model': response.model,
            'id': response.id,
        }
