#!/usr/bin/env bash
# 管理员上线检查（后端 + 契约 + 迁移演练，不含浏览器）
#   bash golive_check.sh --platform /www/wwwroot/smupa_gzpt \
#       --python /www/server/pyporject_evn/.../bin/python \
#       --url https://gzpt.smupa.top \
#       --origin https://kmv-learning-assistant.xyz \
#       --mode all
set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${SMUPA_PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

exec "$PY" "$HERE/golive.py" "$@"
