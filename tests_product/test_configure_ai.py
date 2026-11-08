"""These tests also run with a bare Python environment, without third-party modules."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.configure_ai import set_key, main

class ConfigureAITests(unittest.TestCase):
    def test_preserves_other_settings_and_replaces_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / '.env'
            env.write_text('# Keep this comment\nDATABASE_URL=existing\nOPENAI_API_KEY=old\nexport OPENAI_API_KEY=duplicate\nGROQ_MODEL=test')
            set_key(env, 'OPENAI_API_KEY', 'new-test-key')
            result = env.read_text()
            self.assertIn('# Keep this comment\nDATABASE_URL=existing\n', result)
            self.assertEqual(result.count('OPENAI_API_KEY='), 1)
            self.assertIn("OPENAI_API_KEY='new-test-key'\n", result)
            self.assertIn('GROQ_MODEL=test', result)
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_escapes_secret_and_appends_after_missing_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / '.env'
            env.write_text('GROQ_MODEL=test')
            set_key(env, 'GEMINI_API_KEY', "fake'key\\value")
            self.assertEqual(env.read_text(), "GROQ_MODEL=test\nGEMINI_API_KEY='fake\\'key\\\\value'\n")

    def test_rejects_newline_without_changing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / '.env'
            env.write_text('KEEP=original\n')
            with self.assertRaises(ValueError):
                set_key(env, 'OPENAI_API_KEY', 'key\nBAD=value')
            self.assertEqual(env.read_text(), 'KEEP=original\n')

    def test_bare_python_import_needs_no_site_packages(self):
        result = subprocess.run([sys.executable, '-S', '-c', 'import scripts.configure_ai'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_masked_setup_preserves_config_without_printing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.env').write_text('DATABASE_URL=existing\n')
            with patch('scripts.configure_ai.ROOT', root), patch('sys.stdin.isatty', return_value=True), patch('scripts.configure_ai.getpass', side_effect=['fake-test-secret', '', '']), patch('builtins.input', side_effect=['test-model', ',', '']), patch('builtins.print') as output:
                main()
            self.assertNotIn('fake-test-secret', str(output.call_args_list))
            self.assertIn('DATABASE_URL=existing', (root / '.env').read_text())
            self.assertIn("OPENAI_MODEL='test-model'", (root / '.env').read_text())

if __name__ == '__main__':
    unittest.main()
