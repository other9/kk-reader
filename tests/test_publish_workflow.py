"""Exercise the actual workflow's publication shell against a local bare remote."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_bot_push_never_overwrites_concurrent_manual_data(tmp_path):
    bash = Path("C:/Program Files/Git/bin/bash.exe") if os.name == "nt" else None
    executable = str(bash) if bash and bash.exists() else shutil.which("bash")
    if not executable:
        pytest.skip("bash is required to exercise the Actions publication step")
    remote, owner, bot = (tmp_path / name for name in ("remote.git", "owner", "bot"))
    git(tmp_path, "init", "--bare", str(remote))
    git(tmp_path, "clone", str(remote), str(owner))
    git(owner, "checkout", "-b", "main")
    git(owner, "config", "user.name", "Test")
    git(owner, "config", "user.email", "test@example.invalid")
    git(owner, "config", "commit.gpgsign", "false")
    data = owner / "docs/data"
    data.mkdir(parents=True)
    for name in ("feeds.json", "articles.json"):
        (data / name).write_text("{}")
    git(owner, "add", ".")
    git(owner, "commit", "-m", "base")
    git(owner, "push", "-u", "origin", "main")
    git(tmp_path, "clone", "--branch", "main", str(remote), str(bot))
    git(bot, "config", "commit.gpgsign", "false")

    # Operator disables a feed while an older bot checkout is generating data.
    (data / "feeds.json").write_text('{"active": false}')
    git(owner, "add", ".")
    git(owner, "commit", "-m", "manual disable")
    git(owner, "push")
    expected = git(owner, "rev-parse", "HEAD")
    (bot / "docs/data/feeds.json").write_text('{"active": true}')

    workflow = (Path(__file__).resolve().parents[1] /
                ".github/workflows/fetch-feeds.yml").read_text(encoding="utf-8")
    section = workflow.split("- name: Commit updated data", 1)[1]
    script = section.split("run: |", 1)[1]
    script = "\n".join(line[10:] for line in script.splitlines() if line.strip())
    result = subprocess.run([executable, "-e", "-c", script], cwd=bot,
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert git(remote, "rev-parse", "main") == expected
    assert git(remote, "show", "main:docs/data/feeds.json") == '{"active": false}'
