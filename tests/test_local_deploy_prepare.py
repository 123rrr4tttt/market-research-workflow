from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = Path('main/backend/requirements.txt')
FRONTEND_LOCK = Path('main/frontend-modern/pnpm-lock.yaml')
WEBUI_LOCK = Path('main/ops/codex-webui/pnpm-lock.yaml')
DEPENDENCY_DIRS = (
    Path('main/backend/.venv311'),
    Path('main/frontend-modern/node_modules'),
    Path('main/ops/codex-webui/node_modules'),
)


def snapshot(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob('*') if path.is_file()}


@pytest.mark.parametrize('failure', ('existing-conflict', 'link-failure', 'lock-mismatch'))
def test_prepare_rejects_unusable_dependency_source_without_altering_it(
    tmp_path: Path, failure: str,
) -> None:
    candidate = tmp_path / 'checkout'
    source = tmp_path / 'dependency-source'
    for relative in (Path('scripts/local-deploy.sh'), Path('main/backend/start-local.sh'),
                     REQUIREMENTS, FRONTEND_LOCK, WEBUI_LOCK):
        (candidate / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, candidate / relative)
    for relative in (REQUIREMENTS, FRONTEND_LOCK, WEBUI_LOCK):
        (source / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(candidate / relative, source / relative)
    for relative in DEPENDENCY_DIRS:
        (source / relative).mkdir()
        (source / relative / 'sentinel').write_bytes(b'keep source\n')
    (source / DEPENDENCY_DIRS[0] / '.requirements.sha256').write_text(
        hashlib.sha256((candidate / REQUIREMENTS).read_bytes()).hexdigest() + '\n', encoding='utf-8',
    )

    env = dict(os.environ, MRW_DEPENDENCY_SOURCE_ROOT=str(source), HOME=str(tmp_path))
    existing = candidate / DEPENDENCY_DIRS[0]
    link_log = tmp_path / 'attempted-link'
    if failure == 'existing-conflict':
        existing.mkdir()
        (existing / 'sentinel').write_bytes(b'keep candidate\n')
    elif failure == 'link-failure':
        fake_bin = tmp_path / 'bin'
        fake_bin.mkdir()
        ln = fake_bin / 'ln'
        ln.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$MRW_LINK_LOG"\nexit 73\n', encoding='utf-8')
        ln.chmod(0o755)
        env.update(PATH=f'{fake_bin}:{env["PATH"]}', MRW_LINK_LOG=str(link_log))
    else:
        with (source / FRONTEND_LOCK).open('ab') as lock:
            lock.write(b'\n# incompatible dependency source\n')

    before = snapshot(source)
    result = subprocess.run(
        [str(candidate / 'scripts/local-deploy.sh'), 'prepare'],
        cwd=candidate, env=env, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert snapshot(source) == before
    for relative in DEPENDENCY_DIRS[1:]:
        assert not os.path.lexists(candidate / relative)
    assert not (candidate / 'main/backend/.env').exists()
    if failure == 'existing-conflict':
        assert '当前根已有不同依赖目录' in result.stdout
        assert not existing.is_symlink()
        assert (existing / 'sentinel').read_bytes() == b'keep candidate\n'
    else:
        assert not os.path.lexists(existing)
        if failure == 'link-failure':
            assert link_log.read_text(encoding='utf-8').splitlines() == [
                '-s', str((source / DEPENDENCY_DIRS[0]).resolve()), str(existing.resolve()),
            ]
            assert '✅ 复用 backend venv' not in result.stdout
        else:
            assert '依赖来源 frontend pnpm-lock.yaml 与当前候选不一致' in result.stdout
