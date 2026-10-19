# Mac dotfiles

这台 Apple Silicon Mac 的开发配置，初次整理于 2026-09-30。

## 保存的内容

- `Brewfile`：Homebrew 导出的软件清单，包括 gh、jq、mise、ripgrep。
- `config/zprofile`：Homebrew PATH。
- `config/zshrc`：mise 的 zsh 集成。
- `config/gitconfig`：当前 Git 配置，包含个人姓名和邮箱；公开仓库前请确认愿意公开。
- `config/mise/config.toml`：当前运行时配置 `node = "lts"`。
- `scripts/restore.sh`：预览或恢复配置，覆盖前自动备份。
- `scripts/sync.sh`：把本机最新的软件清单和配置副本同步到仓库。
- `scripts/auto-sync.py`：每日自动同步配置，有变化时提交并推送到 `origin/master`。
- `scripts/macos.sh`：关闭自动纠正、智能引号、智能破折号。
- `APPS.md`：非 Homebrew 管理的软件清单及安装入口。

## 在下一台 Mac 上恢复

以下命令以仓库位置 `~/repos/dotsfiles` 为例。

1. 安装 Command Line Tools：`xcode-select --install`。
2. 按 https://brew.sh 的官方说明安装 Homebrew，并完成安装器提示的 shellenv 配置。
3. 从自己的 Git 远程克隆本仓库，或者把仓库复制到新电脑。
4. 安装清单中的命令行工具：

   ```bash
   cd ~/repos/dotsfiles
   brew bundle --file=Brewfile
   ```

5. 先检查 `config/gitconfig` 的身份和其他配置，然后预览并恢复：

   ```bash
   ./scripts/restore.sh
   ./scripts/restore.sh --apply
   ```

   脚本使用复制，不建立软链接。已有文件若不同，会先备份到
   `~/.local/state/dotfiles/backup.*`，并在终端打印路径。
   恢复会替换整个目标文件；如新电脑已有其他配置，请先手动合并。

6. 打开一个新终端，安装运行时并验证：

   ```bash
   mise install
   mise doctor
   node --version
   gh --version
   ```

7. 按需要应用 macOS 输入偏好，再重新打开相关应用：

   ```bash
   ./scripts/macos.sh
   ./scripts/macos.sh --apply
   ```

8. 按 `APPS.md` 安装 GUI 软件；使用 `gh auth login` 登录 GitHub。
   编辑器账户、SSH 密钥、服务 Token 等单独恢复，不在本仓库中。

这些 shell 配置按当前 Apple Silicon 的 `/opt/homebrew` 路径保存。
如果恢复到 Intel Mac，需先将两份 zsh 配置中的路径调整为实际 Homebrew 路径。

## 版本说明

整理时 Node 为 `24.21.0`，npm 为 `11.19.0`。全局配置保存的是 `lts`，
未来执行安装可能得到更新的 LTS，因此这份配置不是软件版本的完整快照。
需要精确复现的项目应在项目仓库中固定 Node 和包管理器版本，并提交 lockfile。
Homebrew 清单同样通常安装届时可用的版本。

## 更新配置

修改本机设置或通过 Homebrew 安装、卸载软件后，执行：

```bash
cd ~/repos/dotsfiles
./scripts/sync.sh
```

也可以在任意目录执行 `~/repos/dotsfiles/scripts/sync.sh`。
脚本自动导出 Brewfile，更新上面列出的四份配置，并显示 Git 状态。
它会覆盖仓库中的对应副本；如果正在仓库里编辑这些文件，请先处理好修改再同步。
源文件不存在时跳过并保留仓库副本；如需同步删除，请手动删除对应副本并更新恢复脚本。
相同内容不会重复写入。脚本不会自动暂存、提交或推送。

检查后手动提交：

```bash
git diff
git status --short
git add Brewfile config/ scripts/sync.sh README.md
git commit -m "Update development environment"
git push
```

第一次提交时也应加入 `.gitignore`、`APPS.md` 和其他恢复脚本；
未跟踪文件不会出现在普通 `git diff` 中，需要单独检查。
推送前需配置好远程仓库。官网或 App Store 安装的软件仍需手动更新 `APPS.md`；
其他系统设置不由此脚本自动导出。

提交前检查差异，确保没有 Token、密码、SSH 私钥或包含凭证的环境变量。
`.gitignore` 只提供基础排除规则，不能代替内容检查。
不要把整个 `.ssh`、`.config` 或应用数据目录直接加入仓库。

### 每日自动同步

运行 `./scripts/check-sync.sh` 可以只检查是否需要同步。它将本机 Homebrew
清单和上述四份配置与仓库副本比较，并单独列出仓库未提交修改；不会执行同步、
提交或推送，也不会输出配置内容。其他应用及其配置仍需人工核对 `APPS.md`。

每日任务运行 `python3 scripts/auto-sync.py`：先获取并快进到 `origin/master`，
再同步上述五个文件；有变化时创建 `Sync development configuration` 提交并推送。
没有变化时不创建提交。推送失败会保留本地提交，下次运行重试。

自动任务调用 `sync.sh --list-files` 获取同步范围，再调用
`sync.sh --output-dir <临时目录>` 生成副本。凭证检查通过后，才将变化写入仓库并提交。
文件映射和 Homebrew 导出逻辑统一维护在 `sync.sh`；直接运行 `./scripts/sync.sh`
仍按原方式更新仓库副本，不会提交或推送。

自动任务要求工作区干净且位于 `master` 分支。存在未提交/未跟踪修改、分支分叉、
非自动同步产生的未推送提交或疑似凭证时，停止并在结果文件中记录原因。
凭证检查覆盖常见 Token、私钥、凭证赋值和 URL，不能保证识别所有敏感内容。
源配置缺失时保留仓库副本，不自动同步删除；不会强制推送。

这台 Mac 已设置用户级 launchd 任务 `com.syfee.dotsfiles.check-sync`，每天本地时间
09:00 运行（设置时为 Asia/Shanghai，北京时间）。最近一次结果保存在
`~/Library/Logs/dotsfiles-config-check/latest.txt`。任务配置位于
`~/Library/LaunchAgents/com.syfee.dotsfiles.check-sync.plist`，需用户已登录；
不依赖 Codex 应用运行。移动仓库后需更新任务配置中的路径；新电脑需重新设置。
任务使用系统 Python 3、Homebrew 和 Git；GitHub SSH 认证必须可在无交互模式下使用。

查看结果：

```bash
cat ~/Library/Logs/dotsfiles-config-check/latest.txt
```

停止每日检查：

```bash
launchctl bootout "gui/$(id -u)/com.syfee.dotsfiles.check-sync"
```

上述命令停止当前登录会话中的任务；如要阻止以后登录时再次加载，将对应的
`.plist` 文件移出 `~/Library/LaunchAgents/`。

## 仍需手动配置

- FileVault、恢复方式和 Time Machine 备份目的地。
- Cursor 的设置同步、扩展和登录。
- 应用权限、快捷键、浏览器账号和同步。

本仓库不包含整机数据或账户凭证，整机备份由 Time Machine 等工具负责。
