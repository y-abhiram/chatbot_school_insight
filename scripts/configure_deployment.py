"""Create a NEW deployment configuration; never overwrite keys or local .env."""
import argparse
import os
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def configure(domain='', email='', local=False, port=3080):
    if not 1024 <= port <= 65535:
        raise ValueError('Choose a web port from 1024 to 65535.')
    if not local and (not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?', domain)
                      or '.' not in domain or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
        raise ValueError('Provide a DNS hostname and certificate contact email, or use --local-http for a local test.')
    config = ROOT / '.env.production'
    folder = ROOT / '.secrets'
    if config.exists() or folder.exists():
        raise ValueError('Deployment configuration already exists. Edit it in place; refusing to rotate or overwrite secrets.')
    folder.mkdir(mode=0o700)
    for name in ('postgres_password', 'app_password', 'query_password', 'openai_api_key', 'gemini_api_key', 'groq_api_key'):
        value = secrets.token_urlsafe(48) if name.endswith('password') else ''
        # Compose file-backed secrets retain host file modes. The host directory is
        # private; mounted files must be readable by the non-root application UID.
        fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(fd, 'w') as output:
            output.write(value)
        (folder / name).chmod(0o444)
    origin = f'http://localhost:{port}' if local else f'https://{domain}'
    text = f'''# Non-secret runtime settings. API keys belong only in .secrets/ files.
WEB_PORT={port}
PRODUCT_WEB_ORIGINS={origin}
COOKIE_SECURE={'false' if local else 'true'}
SITE_DOMAIN={domain}
SITE_CONTACT_EMAIL={email}
AI_PROVIDER=auto
OPENAI_MODEL=
OPENAI_MODELS=
GEMINI_MODEL=
GEMINI_MODELS=
GROQ_MODEL=
GROQ_MODELS=
IMAGE_TAG=local
'''
    fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write(text)
    print('Created .env.production and private .secrets/. Existing .env and databases are unchanged.')
    print('Enter a provider key in its secret file and the allowed model ID in .env.production before using AI chat.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='')
    parser.add_argument('--email', default='')
    parser.add_argument('--local-http', action='store_true')
    parser.add_argument('--port', type=int, default=3080)
    args = parser.parse_args()
    try:
        configure(args.domain, args.email, args.local_http, args.port)
    except ValueError as error:
        raise SystemExit(str(error))
