"""Portable, dependency-free Codex settings sync. Python 3.11+."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import tomllib
import uuid

ROOT = Path(__file__).resolve().parents[1]
BEGIN = '<!-- workbook-codex:begin -->'
END = '<!-- workbook-codex:end -->'
ALLOWED = {'model_reasoning_effort', 'tool_output_token_limit'}
TARGETS = ('config.toml', 'AGENTS.md')


class SyncError(Exception):
    pass


def sha(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def decode(data: bytes) -> str:
    try:
        return data.decode('utf-8-sig', errors='strict')
    except UnicodeError:
        raise SyncError('File is not valid UTF-8; no automatic encoding conversion.') from None


def normalized_hash(data: bytes) -> str:
    return sha(decode(data).replace('\r\n', '\n').strip().encode('utf-8'))


def parse_toml(data: bytes) -> dict:
    try:
        return tomllib.loads(decode(data))
    except tomllib.TOMLDecodeError:
        raise SyncError('TOML is invalid; inspect locally. Source lines are not printed.') from None


def read_optional(path: Path) -> bytes | None:
    if path.is_symlink():
        raise SyncError(f'{path.name} is a symlink; review its real target manually.')
    if path.exists() and not path.is_file():
        raise SyncError(f'{path.name} is not a regular file.')
    return path.read_bytes() if path.exists() else None


def load_profile(root: Path = ROOT) -> tuple[dict, bytes]:
    profile = json.loads((root / 'portable/settings.json').read_text(encoding='utf-8-sig'))
    settings = profile.get('settings', {})
    if profile.get('schema_version') != 1 or set(settings) != ALLOWED:
        raise SyncError('Unsupported profile schema/settings; refusing additional configuration keys.')
    if settings['model_reasoning_effort'] != 'xhigh' or type(settings['tool_output_token_limit']) is not int or settings['tool_output_token_limit'] <= 0:
        raise SyncError('Invalid portable settings.')
    if not re.fullmatch(r'[0-9A-Za-z._-]+', profile.get('release', '')):
        raise SyncError('Invalid release identifier.')
    path = (root / profile['rules']).resolve()
    if not path.is_relative_to(root.resolve()):
        raise SyncError('Rules path escapes the repository.')
    rules = path.read_bytes()
    text = decode(rules)
    if not text.strip() or BEGIN in text or END in text:
        raise SyncError('Portable rules are empty or contain reserved markers.')
    return profile, rules


def merge_config(original: bytes, settings: dict) -> bytes:
    before = parse_toml(original)
    if all(before.get(key) == value for key, value in settings.items()):
        return original
    text = decode(original)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines(keepends=True)
    boundary = next((i for i, line in enumerate(lines) if line.lstrip().startswith('[')), len(lines))
    changed = set()
    for i, line in enumerate(lines[:boundary]):
        body = line.rstrip('\r\n')
        eol = line[len(body):]
        for key, value in settings.items():
            pattern = r'^(\s*' + re.escape(key) + r'\s*=\s*)("(?:[^"\\]|\\.)*"|\x27[^\x27]*\x27|[+-]?\d[\d_]*)(\s*(?:#.*)?)$'
            match = re.fullmatch(pattern, body)
            if match:
                if key in changed:
                    raise SyncError('Duplicate setting assignment.')
                if before.get(key) != value:
                    lines[i] = match[1] + json.dumps(value) + match[3] + eol
                changed.add(key)
    for key in settings:
        if key in before and before[key] != settings[key] and key not in changed:
            raise SyncError('A managed key uses a nonstandard/multiline syntax; review manually.')
    missing = [f'{key} = {json.dumps(value)}{newline}' for key, value in settings.items() if key not in before]
    # Missing top-level keys are inserted at the start, never inside a table.
    candidate = ('\ufeff' if original.startswith(b'\xef\xbb\xbf') else '') + ''.join(missing + lines)
    result = candidate.encode('utf-8')
    expected = dict(before)
    expected.update(settings)
    if parse_toml(result) != expected:
        raise SyncError('Unexpected semantic change; complex TOML requires manual review.')
    return result


def merge_rules(original: bytes, rules: bytes, profile: dict) -> tuple[bytes, str]:
    text = decode(original)
    newline = '\r\n' if '\r\n' in text else '\n'
    content = decode(rules).replace('\r\n', '\n').strip().replace('\n', newline)
    block = newline.join((BEGIN, f'<!-- release:{profile["release"]} -->', content, END))
    starts = list(re.finditer(r'(?m)^' + re.escape(BEGIN) + r'(?=\r?$)', text))
    ends = list(re.finditer(r'(?m)^' + re.escape(END) + r'(?=\r?$)', text))
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0].end() >= ends[0].start():
            raise SyncError('Managed rule markers are incomplete or duplicated; no write.')
        updated = text[:starts[0].start()] + block + text[ends[0].end():]
        mode = 'update-managed-block'
    elif not text.strip() or normalized_hash(original) in profile.get('known_rules_sha256', []) or normalized_hash(original) == normalized_hash(rules):
        updated = block + newline
        mode = 'adopt-known-rules'
    else:
        updated = text + (newline if text.endswith(('\n', '\r')) else newline * 2) + block + newline
        mode = 'preserve-local-rules-and-append'
    if original.startswith(b'\xef\xbb\xbf'):
        updated = '\ufeff' + updated
    return updated.encode('utf-8'), mode


def plan(home: Path, root: Path = ROOT) -> tuple[dict, dict, dict]:
    profile, rules = load_profile(root)
    before = {name: read_optional(home / name) for name in TARGETS}
    config = merge_config(before['config.toml'] or b'', profile['settings'])
    merged_rules, mode = merge_rules(before['AGENTS.md'] or b'', rules, profile)
    after = {'config.toml': config, 'AGENTS.md': merged_rules}
    report = {
        'release': profile['release'],
        'changes': [name for name in TARGETS if before[name] != after[name]],
        'settings': profile['settings'],
        'rules_mode': mode,
        'local_rules_review_needed': mode == 'preserve-local-rules-and-append',
        'preserved': ['model', 'plugins', 'MCP', 'memories', 'permissions', 'unmanaged rules'],
    }
    return report, before, after


@contextmanager
def locked(home: Path):
    home.mkdir(parents=True, exist_ok=True)
    lock = home / '.workbook-sync.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise SyncError('Another sync/restore holds the lock; do not remove it without checking.') from None
    os.close(fd)
    try:
        yield
    finally:
        lock.unlink()


def atomic_write(path: Path, data: bytes, mode: int | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix='.workbook-', dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def apply(home: Path, root: Path = ROOT) -> dict:
    with locked(home):
        report, before, after = plan(home, root)
        if not report['changes']:
            return {**report, 'applied': False, 'reason': 'already-current'}
        backup_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        backup = home / 'workbook-backups' / backup_id
        backup.mkdir(parents=True, mode=0o700)
        receipt = {'schema_version': 1, 'release': report['release'], 'files': {}}
        for name in report['changes']:
            target = home / name
            mode = stat.S_IMODE(target.stat().st_mode) if before[name] is not None else 0o600
            if before[name] is not None:
                atomic_write(backup / (name + '.before'), before[name], 0o600)
            receipt['files'][name] = {'before_hash': sha(before[name]), 'after_hash': sha(after[name]), 'before_mode': mode}
        atomic_write(backup / 'receipt.json', json.dumps(receipt, indent=2).encode('utf-8'), 0o600)
        written = []
        try:
            for name in report['changes']:
                if read_optional(home / name) != before[name]:
                    raise SyncError('File changed since planning; aborting to preserve concurrent edits.')
                atomic_write(home / name, after[name], receipt['files'][name]['before_mode'])
                written.append(name)
            if any(read_optional(home / name) != after[name] for name in report['changes']):
                raise SyncError('Post-write verification failed.')
        except Exception:
            for name in reversed(written):
                if read_optional(home / name) == after[name]:
                    if before[name] is None:
                        (home / name).unlink()
                    else:
                        atomic_write(home / name, before[name], receipt['files'][name]['before_mode'])
            raise
        return {**report, 'applied': True, 'backup_id': backup_id, 'verified': True}


def restore(home: Path, backup_id: str) -> dict:
    if not re.fullmatch(r'[0-9A-Za-z._-]+', backup_id) or backup_id in ('.', '..'):
        raise SyncError('Invalid backup id.')
    backups = (home / 'workbook-backups').resolve()
    backup = (backups / backup_id).resolve()
    if not backup.is_relative_to(backups):
        raise SyncError('Backup path escapes the backup directory.')
    receipt = json.loads((backup / 'receipt.json').read_text(encoding='utf-8'))
    files = receipt.get('files', {})
    if not files or not set(files).issubset(TARGETS):
        raise SyncError('Unexpected backup targets.')
    with locked(home):
        originals = {}
        for name, item in files.items():
            if sha(read_optional(home / name)) != item['after_hash']:
                raise SyncError('A file changed after installation; restore would overwrite later edits.')
            original = (backup / (name + '.before')).read_bytes() if item['before_hash'] is not None else None
            if sha(original) != item['before_hash']:
                raise SyncError('Backup content hash mismatch; no restore.')
            originals[name] = original
        for name, original in originals.items():
            if original is None:
                (home / name).unlink()
            else:
                atomic_write(home / name, original, files[name]['before_mode'])
    return {'restored': True, 'files': list(files)}


def check(home: Path, root: Path = ROOT) -> dict:
    report, before, after = plan(home, root)
    config = parse_toml(before['config.toml'] or b'')
    plugins = config.get('plugins', {})
    return {
        **report, 'current': not report['changes'],
        'settings_match': {key: config.get(key) == value for key, value in report['settings'].items()},
        'fingerprints': {name: sha(data) for name, data in before.items()},
        'configured_plugins': len(plugins),
        'enabled_plugins': sum(item.get('enabled', True) for item in plugins.values()),
        'runtime_budget_verified': False,
        'model_xhigh_support': 'not-verified; confirm selected model/client supports xhigh',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'apply', 'check', 'restore'):
        sub = commands.add_parser(name)
        sub.add_argument('--codex-home', type=Path)
        if name == 'restore':
            sub.add_argument('--backup', required=True)
    args = parser.parse_args()
    home = args.codex_home or (Path(os.environ['CODEX_HOME']) if os.environ.get('CODEX_HOME') else Path.home() / '.codex')
    try:
        if args.command == 'plan':
            result = plan(home)[0]
        elif args.command == 'apply':
            result = apply(home)
        elif args.command == 'check':
            result = check(home)
        else:
            result = restore(home, args.backup)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except SyncError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=True))
        return 1
    except (OSError, ValueError, KeyError, TypeError):
        # Exception text from TOML or filesystem APIs may contain private source data.
        print(json.dumps({'ok': False, 'error': 'Sync refused or failed. Inspect local files/format, lock, and backups; no source content is printed.'}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
