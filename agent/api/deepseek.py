"""
DeepSeek Provider Configurations for Firma-KI Gateway
Optimized for text generation, standard data extraction, and cost-efficiency.
"""

DEEPSEEK_CONFIGS = {
    "deepseek-chat": {
        "description": "General purpose model (DeepSeek-V3), ideal for Tier 1 processing.",
        "parameters": {
            "temperature": 0.3,
            "top_p": 0.9,
            "max_tokens": 4096,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        },
        "throughput": {
            "rpm": 100,
            "tpm": 100000,
        }
    },
    "deepseek-coder": {
        "description": "Specialized model for code generation and technical summarization.",
        "parameters": {
            "temperature": 0.1,
            "top_p": 0.95,
            "max_tokens": 8192,
        },
        "throughput": {
            "rpm": 50,
            "tpm": 50000,
        }
    }
}

def get_optimized_config(model_name: str):
    """Returns the best configuration for the requested DeepSeek model."""
    return DEEPSEEK_CONFIGS.get(model_name, DEEPSEEK_CONFIGS["deepseek-chat"])
