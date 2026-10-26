"""Record local task metrics; never call a model or upload samples."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys


def validate(sample):
    for key in ('task_id', 'family', 'model', 'effort', 'basis', 'source'):
        value = sample.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
            raise ValueError('Use short labels without source text, credentials or control characters.')
    if sample.get('group') not in ('before', 'after') or type(sample.get('success')) is not bool:
        raise ValueError('Invalid group/success.')
    for key in ('input_tokens', 'cached_tokens', 'output_tokens', 'tool_calls', 'retries'):
        value = sample.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError('Metrics must be nonnegative integers or unknown.')
    elapsed = sample.get('elapsed_seconds')
    if elapsed is not None and (not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not math.isfinite(elapsed) or elapsed < 0):
        raise ValueError('Elapsed time must be finite and nonnegative.')
    if sample.get('cached_tokens') is not None and sample.get('input_tokens') is not None and sample['cached_tokens'] > sample['input_tokens']:
        raise ValueError('Cached tokens are a subset of input tokens, not additional input.')


def read_samples(path):
    if not path.exists():
        return []
    samples = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    for sample in samples:
        validate(sample)
    return samples


def record(path, sample):
    validate(sample)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        samples = read_samples(path)
        if any((item['group'], item['task_id']) == (sample['group'], sample['task_id']) for item in samples):
            raise ValueError('Duplicate task id in this group; no overwrite.')
        row = dict(sample, recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps(row, ensure_ascii=True) + '\n')
    finally:
        lock.unlink()


def aggregate(samples):
    successes = sum(row['success'] for row in samples)
    known = all(row.get('input_tokens') is not None and row.get('output_tokens') is not None for row in samples)
    total = sum(row['input_tokens'] + row['output_tokens'] for row in samples) if known else None
    return {
        'tasks': len(samples), 'successes': successes,
        'success_rate': successes / len(samples) if samples else None,
        'total_tokens': total,
        'tokens_per_success': total / successes if total is not None and successes else None,
        'cached_tokens': sum(row['cached_tokens'] for row in samples) if all(row.get('cached_tokens') is not None for row in samples) else None,
    }


def report(samples):
    cohorts = defaultdict(lambda: defaultdict(list))
    identities = set()
    for row in samples:
        validate(row)
        identity = (row['group'], row['task_id'])
        if identity in identities:
            raise ValueError('Duplicate task id; comparison refused.')
        identities.add(identity)
        cohort = tuple(row[key] for key in ('family', 'model', 'effort', 'basis'))
        cohorts[cohort][row['group']].append(row)
    result = []
    for key, groups in sorted(cohorts.items()):
        stats = {name: aggregate(rows) for name, rows in groups.items()}
        before = stats.get('before', {})
        after = stats.get('after', {})
        comparable = before.get('tasks', 0) >= 3 and after.get('tasks', 0) >= 3
        baseline = before.get('tokens_per_success')
        optimized = after.get('tokens_per_success')
        quality_ok = comparable and after['success_rate'] >= before['success_rate']
        reduction = (1 - optimized / baseline) * 100 if quality_ok and baseline and optimized is not None else None
        result.append({'cohort': dict(zip(('family', 'model', 'effort', 'basis'), key)), 'groups': stats, 'minimum_sample_size_met': comparable, 'success_rate_not_lower': bool(quality_ok), 'tokens_per_success_reduction_percent': reduction})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path(os.environ['CODEX_HOME']) if os.environ.get('CODEX_HOME') else Path.home() / '.codex'
    parser.add_argument('--file', type=Path, default=home / 'workbook' / 'measurements.jsonl')
    commands = parser.add_subparsers(dest='command', required=True)
    sub = commands.add_parser('record')
    for flag in ('task-id', 'family', 'model', 'basis', 'source'):
        sub.add_argument('--' + flag, required=True)
    sub.add_argument('--effort', default='xhigh')
    sub.add_argument('--group', choices=('before', 'after'), required=True)
    outcome = sub.add_mutually_exclusive_group(required=True)
    outcome.add_argument('--success', action='store_true')
    outcome.add_argument('--failed', action='store_true')
    for flag in ('input-tokens', 'cached-tokens', 'output-tokens', 'tool-calls', 'retries'):
        sub.add_argument('--' + flag, type=int)
    sub.add_argument('--elapsed-seconds', type=float)
    commands.add_parser('report')
    args = parser.parse_args()
    try:
        if args.command == 'record':
            sample = {key: getattr(args, key) for key in ('task_id', 'family', 'model', 'effort', 'basis', 'source', 'group', 'success', 'input_tokens', 'cached_tokens', 'output_tokens', 'tool_calls', 'retries', 'elapsed_seconds')}
            record(args.file, sample)
            result = {'recorded': True, 'metrics_unknown_are_null': True}
        else:
            result = {'cohorts': report(read_samples(args.file)), 'limits': 'Observational comparison, not a causal guarantee; verify comparable tasks and environment.'}
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'ok': False, 'error': 'Invalid/duplicate metrics, locked file, or unreadable local data; no private source is printed.'}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
