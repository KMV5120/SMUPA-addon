# SMUPA 管理员上线检查（一键脚本）

不依赖 Node / Chromium；只跑后端、接口契约和迁移演练。

## 前置

- 平台仓库已部署本次 PR（含 `repair_meditation_slots`、`verify_meditation_slots`、`0022` 迁移）。
- 已执行 `python manage.py migrate web`。
- 已配置 `gzpt/local_settings.py` 的 `MEDITATION_SLOT_REPAIR_CUTOFF`（必须带时分）。
- 使用平台自己的 Python 虚拟环境。

## 一键

```bash
cd /www/wwwroot/smupa_gzpt
bash /path/to/SMUPA-addon/tests/golive/golive_check.sh \
    --platform . \
    --python /path/to/smupa_gzpt_venv/bin/python \
    --url https://gzpt.smupa.top \
    --origin https://kmv-learning-assistant.xyz \
    --mode all
```

Windows（Git Bash 同理）：

```bash
bash tests/golive/golive_check.sh --platform D:/.../smupa_gzpt \
    --python D:/.../venv/Scripts/python.exe \
    --mode rehearsal
```

## 模式

| 模式 | 内容 | 是否写生产 |
| --- | --- | --- |
| `--mode preflight` | Django check、迁移状态、CORS/cutoff/notice/static 配置、后端测试、verify 命令 | 否 |
| `--mode rehearsal` | 临时 SQLite：造合成旧数据 → dry-run → apply → 幂等检查 | 否（只写临时库） |
| `--mode post-deploy` | 线上只读 GET/OPTIONS：layout 7 档、notice、周末 slots、CORS、dashboard | 否 |
| `--mode all` | 以上全部（需 `--url`） | 否 |

## 输出

- 控制台逐项 `[PASS]/[FAIL]/[SKIP]`
- `golive-report.json`
- 失败时退出码 1；配置/迁移/演练前置不满足时请先按报告修复

## 安全边界

脚本拒绝：

- 对非临时库执行 `repair_meditation_slots --apply`
- `migrate web zero`、`flush`、`sqlflush`、`dbshell`、`shell`、`collectstatic`
- 启动浏览器 / Chromium
- 写入平台仓库或生产库

演练只使用临时目录里的 SQLite；生产库只做 `showmigrations` / `verify_meditation_slots` 等只读检查。
