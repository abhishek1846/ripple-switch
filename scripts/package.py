"""Package reproducible source, excluding runtime, secrets, and user drafts."""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT = {'.gitignore', 'AGENTS.md', 'README.md', 'LICENSE', 'DEMO.md', 'SUBMISSION.md', 'VERIFICATION.md', 'DESIGN.md', 'package.json', 'ripple.py', 'Start Ripple.command'}
ALLOWED_DIRS = {'.github', 'ripple', 'web', 'agents', 'switch', 'tests', 'scripts', 'workspaces'}
FORBIDDEN = {'.ripple', '__pycache__', '.git', 'uploads', 'node_modules', 'artifacts'}


def source_files():
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(ROOT)
        if any(p in FORBIDDEN for p in rel.parts) or path.suffix == '.pyc':
            continue
        if len(rel.parts) == 1 and rel.name in ALLOWED_ROOT:
            yield path, rel
        elif len(rel.parts) > 1 and rel.parts[0] in ALLOWED_DIRS and path.suffix in {'.py', '.js', '.mjs', '.css', '.html', '.svg', '.md', '.json', '.csv', '.yaml', '.yml', '.txt', '.command'}:
            yield path, rel


def main():
    dest = ROOT / 'artifacts/ripple-source.zip'
    dest.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path, rel in source_files():
            archive.write(path, Path('ripple') / rel)
    print(dest)
    print('SHA256 ' + hashlib.sha256(dest.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
