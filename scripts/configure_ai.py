"""Standard-library-only setup: keys are masked and saved in the ignored .env file."""
import os
import re
import sys
import tempfile
from pathlib import Path
from getpass import getpass

ROOT = Path(__file__).resolve().parents[1]

def set_key(filename, name, value):
    """Replace one single-line dotenv setting, preserving unrelated settings/comments."""
    if not re.fullmatch(r'[A-Z][A-Z0-9_]*', name) or '\n' in value or '\r' in value:
        raise ValueError('Configuration names and values must be single-line settings.')
    env = Path(filename)
    if env.is_symlink():
        raise ValueError('Use a regular .env file, not a symbolic link.')
    text = env.read_text() if env.exists() else ''
    quoted = "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"
    replacement = f'{name}={quoted}\n'
    pattern = re.compile(r'^\s*(?:export\s+)?' + re.escape(name) + r'\s*=')
    lines = text.splitlines(keepends=True)
    updated, found = [], False
    for line in lines:
        if pattern.match(line):
            if not found:
                updated.append(replacement)
                found = True
        else:
            updated.append(line)
    if not found:
        if updated and not updated[-1].endswith('\n'):
            updated[-1] += '\n'
        updated.append(replacement)
    # A private temporary file keeps partial writes and world-readable secrets out of .env.
    fd, temporary = tempfile.mkstemp(prefix='.ai-config-', dir=env.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(''.join(updated))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, env)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run this script in your terminal so API keys can be entered with masked input.')
    env = ROOT / '.env'
    if env.is_symlink():
        raise SystemExit('Use a regular .env file, not a symbolic link.')
    if not env.exists():
        fd = os.open(env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write((ROOT / '.env.example').read_text())
    env.chmod(0o600)
    print('Configure any or all providers. Press Enter to keep existing settings. Keys are never printed.')
    for provider in ['OPENAI', 'GEMINI', 'GROQ']:
        print(f'\n{provider}')
        key = getpass('API key (masked; blank to keep): ').strip()
        models = input('Available model IDs, comma separated (blank to keep): ').strip()
        if key:
            set_key(env, provider + '_API_KEY', key)
        values = [model.strip() for model in models.split(',') if model.strip()]
        if values:
            set_key(env, provider + '_MODEL', values[0])
            set_key(env, provider + '_MODELS', ','.join(values))
    print('\nSaved locally. Restart School Insight, then choose a provider and model in the side panel.')

if __name__ == '__main__':
    main()
