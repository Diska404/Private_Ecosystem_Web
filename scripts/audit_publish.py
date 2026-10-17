"""Inspect the exact staged Git snapshot without printing credential contents."""
from pathlib import Path
import argparse
import re
import subprocess


def audit(root):
    result = subprocess.run(['git', 'ls-files', '--stage', '-z'], cwd=root, capture_output=True, check=True)
    failures = []
    total = 0
    patterns = [
        rb'gh[pousr]_[A-Za-z0-9]{30,}',
        rb'github_pat_[A-Za-z0-9_]{30,}',
        rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        rb'\bAKIA[A-Z0-9]{16}\b',
        rb'\bxox[baprs]-[A-Za-z0-9-]{20,}',
        rb'\bhf_[A-Za-z0-9]{30,}',
        rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{30,}',
    ]
    forbidden_parts = {'.venv', 'node_modules', '.next', '.backups', '.ecosystem', '.r0-dependency-backup', '__pycache__', 'data', 'logs', 'test-results', 'playwright-report'}
    for entry in result.stdout.split(b'\0'):
        if not entry:
            continue
        metadata, filename = entry.split(b'\t', 1)
        mode, digest, stage = metadata.split()
        name = filename.decode('utf-8')
        path = Path(name)
        if stage != b'0' or mode == b'160000':
            failures.append((name, 'unmerged entry or nested repository'))
            continue
        if any(part in forbidden_parts for part in path.parts) or (path.name.startswith('.env') and path.name != '.env.example') or name == 'local-ai-control-center/config/app.json' or path.suffix.lower() in {'.db', '.sqlite', '.sqlite3', '.pyc', '.pem', '.key', '.gguf', '.safetensors', '.zip'} or name.endswith(('-wal', '-shm')):
            failures.append((name, 'local/private/generated file'))
            continue
        content = subprocess.run(['git', 'cat-file', 'blob', digest.decode()], cwd=root, capture_output=True, check=True).stdout
        total += 1
        if content.startswith(b'SQLite format 3\0') or any(re.search(pattern, content) for pattern in patterns):
            failures.append((name, 'possible credential or database content'))
        if len(content) > 25 * 1024 * 1024:
            failures.append((name, 'unexpected file larger than 25 MiB'))
    if failures:
        for name, reason in failures:
            print(f'FAIL {name}: {reason}')
        raise SystemExit(1)
    print(f'PASS staged publish audit: {total} files; no forbidden local data or recognized credential patterns.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    audit(parser.parse_args().repo.resolve())
