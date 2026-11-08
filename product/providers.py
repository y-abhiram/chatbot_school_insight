"""Server-side provider configuration and explicitly allowed models."""
import os
import re

PROVIDERS = {
    'openai': 'OpenAI',
    'gemini': 'Gemini',
    'groq': 'Groq',
}


def models_for(provider):
    prefix = provider.upper()
    values = [os.getenv(prefix + '_MODEL', '')] + os.getenv(prefix + '_MODELS', '').split(',')
    return list(dict.fromkeys(
        value.strip() for value in values
        if value.strip() and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,120}', value.strip())
    ))[:20]


def provider_status():
    return [dict(id=provider, name=name,
                 configured=bool(os.getenv(provider.upper() + '_API_KEY') and models_for(provider)),
                 models=models_for(provider))
            for provider, name in PROVIDERS.items()]


def select_provider(provider='auto', model=''):
    if provider == 'auto':
        preferred = os.getenv('AI_PROVIDER', 'auto')
        provider = preferred if preferred in PROVIDERS else next(
            (entry['id'] for entry in provider_status() if entry['configured']), ''
        )
    if not provider:
        raise ValueError('No AI provider is configured. Add an API key and model on the server, then restart.')
    if provider not in PROVIDERS:
        raise ValueError('Choose OpenAI, Gemini, or Groq.')
    allowed = models_for(provider)
    if not os.getenv(provider.upper() + '_API_KEY') or not allowed:
        raise ValueError(f'{PROVIDERS[provider]} is not configured. Add its API key and model on the server, then restart.')
    if model and model not in allowed:
        raise ValueError('This model is not in the server’s configured model list.')
    return provider, model or allowed[0]
