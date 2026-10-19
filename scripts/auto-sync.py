#!/usr/bin/env python3
"""Capture managed dotfiles, commit changes, and push origin/master."""
import argparse
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parent.parent
FILES = {
    "config/zprofile": ".zprofile",
    "config/zshrc": ".zshrc",
    "config/gitconfig": ".gitconfig",
    "config/mise/config.toml": ".config/mise/config.toml",
}
MANAGED = {"Brewfile", *FILES}
SUBJECT = "Sync development configuration"
ENV = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_ANALYTICS="1",
           GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15")


def run(*args):
    result = subprocess.run(args, cwd=REPO, env=ENV, capture_output=True, text=True, timeout=180)
    if result.returncode:
        # Do not put subprocess output or configuration values in scheduled logs.
        raise RuntimeError(f"命令失败：{' '.join(args[:2])}（退出码 {result.returncode}）；请手动检查。")
    return result.stdout.strip()


def git(*args):
    return run("git", *args)


def check_secrets(name, data):
    """A conservative guard for common credentials, not a complete secret detector."""
    patterns = [
        r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----",
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
        r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}\b",
        r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
        r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
        r"https?://[^\s/@:]+:[^\s/@]+@",
        r"(?i)authorization\s*[:=]\s*['\"]?(?:basic|bearer)\s+[A-Za-z0-9+/=_-]{8,}",
    ]
    assignment = re.compile(
        r"(?i)^\s*(?:export\s+)?[\w.-]*(?:token|secret|password|passwd|api[_-]?key|credential)"
        r"[\w.-]*\s*=\s*(.+)$"
    )
    for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
        if any(re.search(pattern, line) for pattern in patterns):
            raise RuntimeError(f"发现疑似凭证：{name}:{number}，未同步或提交；请人工检查。")
        match = assignment.match(line)
        if match and not line.lstrip().startswith("#"):
            value = match.group(1).strip().strip("\"'")
            # Empty values and references to environment variables do not embed a secret.
            if value and not re.fullmatch(r"\$(?:[A-Za-z_]\w*|\{[A-Za-z_]\w*\})", value):
                raise RuntimeError(f"发现疑似凭证赋值：{name}:{number}，未同步或提交；请人工检查。")


def sync(log):
    if git("branch", "--show-current") != "master":
        raise RuntimeError("当前分支不是 master，已暂停。")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("仓库存在未提交或未跟踪的修改，已暂停以保留现有工作。")
    for state in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        if Path(git("rev-parse", "--git-path", state)).exists():
            raise RuntimeError("仓库正在合并、变基或拣选提交，已暂停。")

    log("获取 origin/master…")
    git("fetch", "--no-tags", "origin", "refs/heads/master:refs/remotes/origin/master")
    # Fast-forward only: never resolve conflicts or force-push unattended.
    git("merge", "--ff-only", "origin/master")
    pending = git("rev-list", "origin/master..HEAD").splitlines()
    for commit in pending:
        paths = set(git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines())
        if git("show", "-s", "--format=%s", commit) != SUBJECT or not paths or not paths <= MANAGED:
            raise RuntimeError("存在非自动同步产生的未推送提交，请先手动处理。")
        # Also inspect pending history: a push uploads earlier blobs, not just HEAD.
        for name in paths:
            check_secrets(name, git("show", f"{commit}:{name}").encode())

    brew = shutil.which("brew")
    if not brew:
        raise RuntimeError("找不到 Homebrew，已停止。")
    with tempfile.TemporaryDirectory(prefix="dotfiles-auto-sync-") as staging:
        dump = Path(staging) / "Brewfile"
        run(brew, "bundle", "dump", f"--file={dump}")
        captures = {"Brewfile": dump.read_bytes()}
        for name, source in FILES.items():
            path = Path.home() / source
            if not path.exists():
                log(f"源文件缺失，保留仓库副本：{name}")
                continue
            if not path.is_file():
                raise RuntimeError(f"源文件不是普通文件：{name}")
            captures[name] = path.read_bytes()

        changed = []
        for name, data in captures.items():
            target = REPO / name
            if target.is_symlink():
                raise RuntimeError(f"仓库副本是软链接：{name}，已暂停。")
            check_secrets(name, data)
            if not target.exists() or target.read_bytes() != data:
                changed.append(name)

        if changed:
            # Recheck after the potentially slow export, before writing anything.
            if git("status", "--porcelain", "--untracked-files=all"):
                raise RuntimeError("检查期间仓库出现修改，已暂停。")
            for name in changed:
                target = REPO / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(captures[name])
                log(f"已同步：{name}")
            git("add", "--", *changed)
            if set(git("diff", "--cached", "--name-only").splitlines()) != set(changed):
                raise RuntimeError("暂存区出现其他修改，已停止提交；请人工检查。")
            git("commit", "-m", SUBJECT, "--only", "--", *changed)
            log(f"已提交：{git('rev-parse', '--short', 'HEAD')}")
        else:
            log("配置无变化，无需新增提交。")

    if git("rev-parse", "HEAD") != git("rev-parse", "origin/master"):
        log("推送到 origin/master…")
        git("push", "origin", "HEAD:refs/heads/master")
        log(f"推送成功：{git('rev-parse', '--short', 'HEAD')}")
    else:
        log("远程已同步。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, help="Write the latest result to this path")
    args = parser.parse_args()
    from datetime import datetime
    lines = []

    def log(message):
        lines.append(message)
        print(message, flush=True)

    code = 0
    lock = None
    try:
        log(f"每日配置同步 — {datetime.now().astimezone().isoformat(timespec='seconds')}")
        os.chdir(REPO)
        lock_path = Path(git("rev-parse", "--git-path", "dotfiles-auto-sync.lock"))
        lock = lock_path.open("a")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        sync(log)
    except BlockingIOError:
        log("已有同步任务运行，本次跳过。")
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        log(f"未完成：{error}")
        code = 1
    finally:
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.report.parent,
                                             prefix=".sync-report-", delete=False) as report:
                report.write("\n".join(lines) + "\n")
            os.replace(report.name, args.report)
        if lock:
            lock.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
