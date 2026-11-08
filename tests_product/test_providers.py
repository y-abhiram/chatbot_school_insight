"""Provider selection works independently of the removed prototype."""
import pytest
from product.providers import select_provider, models_for


def test_configured_default_and_model_allowlist(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_MODEL', 'test-model')
    monkeypatch.setenv('OPENAI_MODELS', 'test-model,second-model,invalid model')
    assert models_for('openai') == ['test-model', 'second-model']
    assert select_provider() == ('openai', 'test-model')
    assert select_provider('openai', 'second-model') == ('openai', 'second-model')
    with pytest.raises(ValueError, match='configured model list'):
        select_provider('openai', 'unapproved-model')


def test_missing_provider_key_is_actionable(monkeypatch):
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    with pytest.raises(ValueError, match='not configured'):
        select_provider('groq')
