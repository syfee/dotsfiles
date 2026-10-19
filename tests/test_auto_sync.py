"""Integration checks using a temporary home, fake brew, and local bare remote."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/auto-sync.py"


class AutoSyncTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-dotfiles-sync-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.home = self.root / "home"
        self.remote = self.root / "remote.git"
        self.repo.mkdir()
        self.home.mkdir()
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        brew = fake_bin / "brew"
        brew.write_text('#!/bin/sh\ncat "$HOME/brew.fixture" > "${3#--file=}"\n')
        brew.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=f"{fake_bin}:{os.environ['PATH']}",
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        self.git("init", "-b", "master")
        self.git("config", "user.name", "Sync Test")
        self.git("config", "user.email", "sync-test@example.invalid")
        (self.repo / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.repo / "scripts/auto-sync.py")
        shutil.copy2(SCRIPT.with_name("sync.sh"), self.repo / "scripts/sync.sh")
        for target, source in {"Brewfile": "brew.fixture", "config/zprofile": ".zprofile",
                               "config/zshrc": ".zshrc", "config/gitconfig": ".gitconfig",
                               "config/mise/config.toml": ".config/mise/config.toml"}.items():
            for path in (self.repo / target, self.home / source):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# original\n")
        self.git("add", ".")
        self.git("commit", "-m", "Initial configuration")
        self.git("init", "--bare", str(self.remote))
        self.git("remote", "add", "origin", str(self.remote))
        self.git("push", "-u", "origin", "master")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, env=self.env,
                                       stderr=subprocess.DEVNULL, text=True).strip()

    def execute(self):
        result = subprocess.run([sys.executable, str(self.repo / "scripts/auto-sync.py"),
                                 "--report", str(self.root / "report.txt")],
                                cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual((self.root / "report.txt").read_text(), result.stdout)
        return result

    def remote_head(self):
        return self.git("--git-dir", str(self.remote), "rev-parse", "refs/heads/master")

    def test_sync_push_and_no_change(self):
        (self.home / ".zshrc").write_text("export EDITOR=vim\n")
        (self.home / "brew.fixture").write_text('brew "example"\n')
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        head = self.git("rev-parse", "HEAD")
        self.assertEqual(self.remote_head(), head)
        self.assertEqual(set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()),
                         {"config/zshrc", "Brewfile"})
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.execute().returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_preserve_dirty_index_and_worktree(self):
        (self.repo / "config/zshrc").write_text("local edit\n")
        self.git("add", "config/zshrc")
        before = self.git("diff", "--cached")
        (self.home / ".zshrc").write_text("machine change\n")
        self.assertNotEqual(self.execute().returncode, 0)
        self.assertEqual(self.git("diff", "--cached"), before)
        self.assertEqual((self.repo / "config/zshrc").read_text(), "local edit\n")

    def test_secret_stops_before_writing_or_logging_value(self):
        secret = "ghp_" + "a" * 36
        (self.home / ".zshrc").write_text(f"export GITHUB_TOKEN={secret}\n")
        before = self.git("rev-parse", "HEAD")
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.remote_head(), before)

    def test_failed_push_retries_existing_commit(self):
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        before = self.remote_head()
        (self.home / ".zshrc").write_text("export EDITOR=vim\n")
        self.assertNotEqual(self.execute().returncode, 0)
        pending = self.git("rev-parse", "HEAD")
        self.assertNotEqual(pending, before)
        self.assertEqual(self.remote_head(), before)
        hook.unlink()
        self.assertEqual(self.execute().returncode, 0)
        self.assertEqual(self.remote_head(), pending)
        self.assertEqual(self.git("rev-parse", "HEAD"), pending)

    def test_refuse_unrelated_pending_commit(self):
        before = self.remote_head()
        (self.repo / "NOTES.md").write_text("manual work\n")
        self.git("add", "NOTES.md")
        self.git("commit", "-m", "Manual change")
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.remote_head(), before)

    def test_fast_forward_remote_before_sync(self):
        (self.repo / "NOTES.md").write_text("remote change\n")
        self.git("add", "NOTES.md")
        self.git("commit", "-m", "Remote change")
        self.git("push")
        self.git("reset", "--hard", "HEAD~1")
        (self.home / ".zshrc").write_text("export EDITOR=vim\n")
        self.assertEqual(self.execute().returncode, 0)
        self.assertEqual((self.repo / "NOTES.md").read_text(), "remote change\n")
        self.assertEqual(self.remote_head(), self.git("rev-parse", "HEAD"))

    def test_diverged_branches_stop(self):
        (self.repo / "remote.txt").write_text("remote\n")
        self.git("add", "remote.txt")
        self.git("commit", "-m", "Remote commit")
        self.git("push")
        before_remote = self.remote_head()
        self.git("reset", "--hard", "HEAD~1")
        (self.repo / "local.txt").write_text("local\n")
        self.git("add", "local.txt")
        self.git("commit", "-m", "Local commit")
        before_local = self.git("rev-parse", "HEAD")
        self.assertNotEqual(self.execute().returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), before_local)
        self.assertEqual(self.remote_head(), before_remote)

    def test_missing_source_retains_copy(self):
        (self.home / ".zshrc").unlink()
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.execute().returncode, 0)
        self.assertEqual((self.repo / "config/zshrc").read_text(), "# original\n")
        self.assertEqual(self.remote_head(), before)

    def test_parallel_run_skips(self):
        with (self.repo / ".git/dotfiles-auto-sync.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.execute()
        self.assertEqual(result.returncode, 0)
        self.assertIn("已有同步任务运行", result.stdout)

    def test_background_export_can_find_mise_shims(self):
        shim = self.home / ".local/share/mise/shims/dotfiles-test-runtime"
        shim.parent.mkdir(parents=True)
        shim.write_text("#!/bin/sh\nexit 0\n")
        shim.chmod(0o755)
        (self.root / "bin/brew").write_text(
            '#!/bin/sh\ncat "$HOME/brew.fixture" > "${3#--file=}"\n'
            'if command -v dotfiles-test-runtime >/dev/null; then\n'
            '  echo \'npm "@example/runtime"\' >> "${3#--file=}"\nfi\n'
        )
        self.assertEqual(self.execute().returncode, 0)
        self.assertIn('npm "@example/runtime"', (self.repo / "Brewfile").read_text())

    def test_snapshot_export_leaves_repository_untouched(self):
        (self.home / ".zshrc").write_text("export EDITOR=vim\n")
        snapshot = self.root / "snapshot with spaces"
        result = subprocess.run(["/bin/bash", str(self.repo / "scripts/sync.sh"),
                                 "--output-dir", str(snapshot)], cwd=self.repo, env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((snapshot / "config/zshrc").read_text(), "export EDITOR=vim\n")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_manual_sync_still_updates_without_committing(self):
        before = self.git("rev-parse", "HEAD")
        (self.home / ".zshrc").write_text("export EDITOR=vim\n")
        result = subprocess.run(["/bin/bash", str(self.repo / "scripts/sync.sh")],
                                cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.repo / "config/zshrc").read_text(), "export EDITOR=vim\n")
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.remote_head(), before)

    def test_new_mapping_in_sync_sh_is_used_automatically(self):
        script = self.repo / "scripts/sync.sh"
        script.write_text(script.read_text()
                          .replace('config_sources=(', 'config_sources=("$HOME/.extra" ', 1)
                          .replace('config_paths=(', 'config_paths=(config/extra ', 1))
        self.git("add", "scripts/sync.sh")
        self.git("commit", "-m", "Add extra config to sync.sh")
        self.git("push")
        (self.home / ".extra").write_text("extra configuration\n")
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.repo / "config/extra").read_text(), "extra configuration\n")
        self.assertEqual(self.remote_head(), self.git("rev-parse", "HEAD"))


if __name__ == "__main__":
    unittest.main()
