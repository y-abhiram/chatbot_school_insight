"""Secrets and deployment initialization must preserve local state."""
import os
import pytest
from product.config import env_value, database_url
from scripts import configure_deployment


def test_database_password_is_url_encoded(monkeypatch):
    monkeypatch.setenv('PRODUCT_DATABASE_HOST', 'postgres')
    monkeypatch.setenv('PRODUCT_DATABASE_PORT', '5432')
    url = database_url('insight_service', 'test:@/secret')
    assert url.host == 'postgres' and url.port == 5432
    assert url.password == 'test:@/secret'
    assert 'test:@/secret' not in url.render_as_string(hide_password=False)


def test_secret_file_and_conflicting_environment(tmp_path, monkeypatch):
    secret = tmp_path / 'key'
    secret.write_text('test-value\n')
    monkeypatch.setenv('TEST_DEPLOY_SECRET_FILE', str(secret))
    assert env_value('TEST_DEPLOY_SECRET') == 'test-value'
    monkeypatch.setenv('TEST_DEPLOY_SECRET', 'other-value')
    with pytest.raises(ValueError, match='either'):
        env_value('TEST_DEPLOY_SECRET')


def test_configuration_does_not_overwrite_local_or_existing_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(configure_deployment, 'ROOT', tmp_path)
    (tmp_path / '.env').write_text('KEEP=existing\n')
    previous_umask = os.umask(0o077)
    try:
        configure_deployment.configure(local=True)
    finally:
        os.umask(previous_umask)
    assert (tmp_path / '.env').read_text() == 'KEEP=existing\n'
    key = tmp_path / '.secrets/postgres_password'
    first = key.read_text()
    assert len(first) >= 48
    assert key.stat().st_mode & 0o777 == 0o444
    assert (tmp_path / '.secrets').stat().st_mode & 0o777 == 0o700
    assert (tmp_path / '.env.production').stat().st_mode & 0o777 == 0o600
    assert 'COOKIE_SECURE=false' in (tmp_path / '.env.production').read_text()
    with pytest.raises(ValueError, match='refusing'):
        configure_deployment.configure(local=True)
    assert key.read_text() == first


def test_public_configuration_requires_https_hostname(tmp_path, monkeypatch):
    monkeypatch.setattr(configure_deployment, 'ROOT', tmp_path)
    with pytest.raises(ValueError):
        configure_deployment.configure(domain='invalid\nsetting', email='admin@example.com')
    configure_deployment.configure(domain='school.example.com', email='admin@example.com')
    config = (tmp_path / '.env.production').read_text()
    assert 'PRODUCT_WEB_ORIGINS=https://school.example.com' in config
    assert 'COOKIE_SECURE=true' in config
