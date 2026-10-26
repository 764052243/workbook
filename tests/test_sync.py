from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import codex_optimize as sync


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.parent = ROOT / '.test-work'
        self.parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.parent)
        self.base = Path(self.temp.name)
        self.home = self.base / 'codex-home'
        self.home.mkdir()

    def tearDown(self):
        self.assertTrue(self.base.resolve().is_relative_to(self.parent.resolve()))
        self.temp.cleanup()

    def put(self, name, data):
        (self.home / name).write_bytes(data)

    def test_plan_does_not_create_missing_home(self):
        absent = self.base / 'absent'
        result = sync.plan(absent)[0]
        self.assertEqual(set(result['changes']), set(sync.TARGETS))
        self.assertFalse(absent.exists())

    def test_apply_new_home_and_idempotence(self):
        first = sync.apply(self.home)
        self.assertTrue(first['verified'])
        state = {name: (self.home / name).read_bytes() for name in sync.TARGETS}
        backups = list((self.home / 'workbook-backups').iterdir())
        second = sync.apply(self.home)
        self.assertFalse(second['applied'])
        self.assertEqual(backups, list((self.home / 'workbook-backups').iterdir()))
        self.assertEqual(state, {name: (self.home / name).read_bytes() for name in sync.TARGETS})
        self.assertTrue(sync.check(self.home)['current'])

    def test_preserves_model_plugins_security_and_private_fields(self):
        original = b'model = "existing-model"\nmodel_reasoning_effort = "high" # keep comment\napproval_policy = "on-request"\n[plugins.example]\nenabled = true\n[mcp_servers.example.env]\nEXAMPLE_SECRET = "SYNTHETIC_TEST_VALUE"\n'
        self.put('config.toml', original)
        before = sync.parse_toml(original)
        sync.apply(self.home)
        after = sync.parse_toml((self.home / 'config.toml').read_bytes())
        for key, value in before.items():
            if key != 'model_reasoning_effort':
                self.assertEqual(value, after[key])
        self.assertIn(b'# keep comment', (self.home / 'config.toml').read_bytes())

    def test_bom_crlf_and_unchanged_quotes_preserved(self):
        original = b'\xef\xbb\xbfmodel = "existing"\r\nmodel_reasoning_effort = \'xhigh\' # unchanged\r\n[plugins.example]\r\nenabled = true\r\n'
        merged = sync.merge_config(original, {'model_reasoning_effort': 'xhigh', 'tool_output_token_limit': 8000})
        self.assertTrue(merged.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b"model_reasoning_effort = 'xhigh' # unchanged\r\n", merged)
        self.assertNotIn(b'\n', merged.replace(b'\r\n', b''))
        self.assertEqual(sync.merge_config(merged, sync.load_profile()[0]['settings']), merged)

    def test_settings_inserted_before_tables(self):
        merged = sync.merge_config(b'[plugins.example]\nenabled = true\n', sync.load_profile()[0]['settings'])
        parsed = sync.parse_toml(merged)
        self.assertEqual(parsed['tool_output_token_limit'], 8000)
        self.assertNotIn('tool_output_token_limit', parsed['plugins']['example'])

    def test_unmanaged_rules_preserved_exactly(self):
        original = '# 本机额外规则\r\n保留原文\r\n'.encode('utf-8')
        self.put('AGENTS.md', original)
        result = sync.apply(self.home)
        self.assertTrue(result['local_rules_review_needed'])
        self.assertTrue((self.home / 'AGENTS.md').read_bytes().startswith(original))

    def test_crlf_managed_block_idempotence(self):
        self.put('AGENTS.md', '# 本机规则\r\n'.encode('utf-8'))
        sync.apply(self.home)
        original = (self.home / 'AGENTS.md').read_bytes()
        result = sync.apply(self.home)
        self.assertFalse(result['applied'])
        self.assertEqual((self.home / 'AGENTS.md').read_bytes(), original)

    def test_symlink_target_refused(self):
        real = self.base / 'real-config.toml'
        real.write_bytes(b'model="example"\n')
        try:
            (self.home / 'config.toml').symlink_to(real)
        except OSError:
            self.skipTest('Creating symlinks is not permitted by this Windows environment.')
        with self.assertRaises(sync.SyncError):
            sync.apply(self.home)
        self.assertEqual(real.read_bytes(), b'model="example"\n')

    def test_known_rules_not_duplicated(self):
        profile, rules = sync.load_profile()
        original = b'\xef\xbb\xbf' + sync.decode(rules).replace('\n', '\r\n').encode('utf-8')
        merged, mode = sync.merge_rules(original, rules, profile)
        self.assertEqual(mode, 'adopt-known-rules')
        self.assertEqual(sync.decode(merged).count('# Codex 全局规范'), 1)

    def test_update_preserves_outside_managed_block(self):
        profile, rules = sync.load_profile()
        managed = sync.merge_rules(b'', rules, profile)[0]
        original = b'local-prefix\n' + managed + b'local-suffix\n'
        updated_profile = dict(profile, release='next-release')
        changed, mode = sync.merge_rules(original, rules + '\n补充规则\n'.encode('utf-8'), updated_profile)
        self.assertTrue(changed.startswith(b'local-prefix\n'))
        self.assertTrue(changed.endswith(b'local-suffix\n'))
        self.assertIn(b'release:next-release', changed)

    def test_bad_markers_refuse_without_modification(self):
        original = (sync.BEGIN + '\nunfinished\n').encode()
        self.put('AGENTS.md', original)
        with self.assertRaises(sync.SyncError):
            sync.apply(self.home)
        self.assertEqual((self.home / 'AGENTS.md').read_bytes(), original)

    def test_invalid_toml_refuses_without_modification(self):
        original = b'model = "unfinished\n'
        self.put('config.toml', original)
        with self.assertRaises(sync.SyncError):
            sync.apply(self.home)
        self.assertEqual((self.home / 'config.toml').read_bytes(), original)
        self.assertFalse((self.home / 'AGENTS.md').exists())

    def test_multiline_source_not_silently_changed(self):
        original = b'developer_instructions = """\nmodel_reasoning_effort = "high"\n"""\nmodel_reasoning_effort = "high"\n'
        self.put('config.toml', original)
        with self.assertRaises(sync.SyncError):
            sync.apply(self.home)
        self.assertEqual((self.home / 'config.toml').read_bytes(), original)

    def test_non_utf8_refuses(self):
        self.put('AGENTS.md', b'\xff\xfe\x00')
        with self.assertRaises(sync.SyncError):
            sync.apply(self.home)

    def test_restore_existing_bytes(self):
        config = b'model="example"\r\n'
        rules = b'local instructions\r\n'
        self.put('config.toml', config)
        self.put('AGENTS.md', rules)
        result = sync.apply(self.home)
        sync.restore(self.home, result['backup_id'])
        self.assertEqual((self.home / 'config.toml').read_bytes(), config)
        self.assertEqual((self.home / 'AGENTS.md').read_bytes(), rules)

    def test_restore_new_files_only(self):
        self.put('untouched.txt', b'preserve')
        result = sync.apply(self.home)
        sync.restore(self.home, result['backup_id'])
        self.assertFalse((self.home / 'config.toml').exists())
        self.assertFalse((self.home / 'AGENTS.md').exists())
        self.assertEqual((self.home / 'untouched.txt').read_bytes(), b'preserve')

    def test_restore_refuses_later_edits(self):
        result = sync.apply(self.home)
        with (self.home / 'AGENTS.md').open('ab') as stream:
            stream.write(b'new local edits\n')
        current = (self.home / 'AGENTS.md').read_bytes()
        with self.assertRaises(sync.SyncError):
            sync.restore(self.home, result['backup_id'])
        self.assertEqual((self.home / 'AGENTS.md').read_bytes(), current)

    def test_restore_tampered_backup_refuses(self):
        self.put('config.toml', b'model="example"\n')
        result = sync.apply(self.home)
        (self.home / 'workbook-backups' / result['backup_id'] / 'config.toml.before').write_bytes(b'tampered')
        with self.assertRaises(sync.SyncError):
            sync.restore(self.home, result['backup_id'])

    def test_restore_traversal_refuses(self):
        with self.assertRaises(sync.SyncError):
            sync.restore(self.home, '../outside')

    def test_active_lock_refuses(self):
        self.put('.workbook-sync.lock', b'')
        with self.assertRaises(sync.SyncError):
            sync.apply(self.home)

    def test_failed_second_write_rolls_back_first(self):
        original = b'model="example"\n'
        self.put('config.toml', original)
        real = sync.atomic_write
        def fail_rules(path, data, mode=None):
            if path == self.home / 'AGENTS.md':
                raise OSError('synthetic failure')
            return real(path, data, mode)
        with patch.object(sync, 'atomic_write', side_effect=fail_rules):
            with self.assertRaises(OSError):
                sync.apply(self.home)
        self.assertEqual((self.home / 'config.toml').read_bytes(), original)
        self.assertFalse((self.home / 'AGENTS.md').exists())

    def test_profile_rejects_extra_settings(self):
        profile, rules = sync.load_profile()
        fake = self.base / 'profile'
        (fake / 'portable').mkdir(parents=True)
        profile['settings']['sandbox_mode'] = 'unsafe-synthetic-value'
        (fake / 'portable/settings.json').write_text(json.dumps(profile), encoding='utf-8')
        (fake / 'portable/global-agents.md').write_bytes(rules)
        with self.assertRaises(sync.SyncError):
            sync.load_profile(fake)


if __name__ == '__main__':
    unittest.main()
