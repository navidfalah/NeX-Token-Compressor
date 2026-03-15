"""
Gemini Provider Configurations for Firma-KI Gateway
Optimized for logical reasoning, deep context, and high-signal data extraction.
"""

GEMINI_CONFIGS = {
    "gemini-1.5-pro": {
        "description": "High-intelligence model for complex logical reasoning and large contexts.",
        "parameters": {
            "temperature": 0.4,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "text/plain",
        },
        "safety_settings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ],
        "throughput": {
            "rpm": 360,
            "tpm": 2000000,
            "rpd": 10000
        }
    },
    "gemini-1.5-flash": {
        "description": "Fast, lightweight model optimized for high-speed, cost-effective tasks.",
        "parameters": {
            "temperature": 0.2,
            "top_p": 0.8,
            "top_k": 40,
            "max_output_tokens": 2048,
        },
        "safety_settings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
        ],
        "throughput": {
            "rpm": 2000,
            "tpm": 1000000,
        }
    }
}

def get_optimized_config(model_name: str):
    """Returns the best configuration for the requested Gemini model."""
    return GEMINI_CONFIGS.get(model_name, GEMINI_CONFIGS["gemini-1.5-flash"])
