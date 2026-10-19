# -*- coding: utf-8 -*-
"""SMUPA 管理员上线检查（后端 + 契约 + 迁移演练，不含浏览器）。

用法：
    python golive.py --platform /www/wwwroot/smupa_gzpt --python /path/venv/bin/python \
        --url https://gzpt.smupa.top --origin https://kmv-learning-assistant.xyz \
        --mode all --workdir /tmp/smupa-golive
"""
from __future__ import print_function

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

PASS, FAIL, SKIP = [], [], []


def say(status, name, detail=''):
    print('[{}] {:<34} {}'.format(status, name, detail))
    if status == 'PASS':
        PASS.append(name)
    elif status == 'FAIL':
        FAIL.append((name, detail))
    else:
        SKIP.append(name)


def run(name, cmd, cwd, env=None, timeout=600):
    print('  $ {}'.format(' '.join(cmd)))
    proc = subprocess.run(
        cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=timeout,
    )
    out = proc.stdout.decode('utf-8', 'replace')
    if proc.returncode != 0:
        print('\n'.join(out.splitlines()[-30:]))
        raise RuntimeError('{} 退出码 {}'.format(name, proc.returncode))
    return out


def base_env(platform, extra_path=None):
    env = os.environ.copy()
    paths = [platform]
    if extra_path:
        paths.insert(0, extra_path)
    env['PYTHONPATH'] = os.pathsep.join(paths)
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['LANG'] = env.get('LANG') or 'C.UTF-8'
    return env


def _write_test_settings(tmp):
    """生成只连临时 SQLite 的测试 settings（不碰生产库）。"""
    path = os.path.join(tmp, 'golive_settings.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(
            "from gzpt.settings import *  # noqa\n"
            "import os\n"
            "_db = os.path.join(os.path.dirname(__file__), 'test.sqlite3')\n"
            "DATABASES = {'default': {'ENGINE': "
            "'django.db.backends.sqlite3', 'NAME': _db, "
            "'TEST': {'NAME': os.path.join(os.path.dirname(__file__), "
            "'test_runner.sqlite3')}}}\n"
            "_root = os.path.abspath(os.path.dirname(__file__))\n"
            "if not os.path.abspath(_db).startswith(_root + os.sep):\n"
            "    raise RuntimeError('refusing non-temp DB: ' + _db)\n"
            "CACHES = {'default': {'BACKEND': "
            "'django.core.cache.backends.locmem.LocMemCache'}}\n"
            "EMAIL_BACKEND = "
            "'django.core.mail.backends.locmem.EmailBackend'\n"
            "STATIC_ROOT = os.path.join(os.path.dirname(__file__), "
            "'static_root')\n"
            "DEBUG = False\n"
            "MEDITATION_CLOSED_DATES = []\n"
            "MEDITATION_SLOT_REPAIR_CUTOFF = ''\n"
            "_DROP_APPS = {'simpleui', 'django_celery_results'}\n"
            "INSTALLED_APPS = [a for a in INSTALLED_APPS "
            "if a not in _DROP_APPS]\n"
        )
    return path


def _read_settings(platform, py):
    # 只 import settings 模块，不 django.setup()：避免因本地缺少 simpleui
    # 等可选 app 而误报；这里只读配置，不连接业务库。
    code = (
        'import json;'
        'import gzpt.settings as s;'
        'print(json.dumps({'
        '"cors": list(getattr(s,"MEDITATION_CORS_ORIGINS",[])),'
        '"closed": getattr(s,"MEDITATION_CLOSED_DATES",[]),'
        '"cutoff": getattr(s,"MEDITATION_SLOT_REPAIR_CUTOFF",""),'
        '"notice": bool(getattr(s,"MEDITATION_NOTICE_HTML","")),'
        '"white": list(getattr(s,"WHITE_REGEX_URL_LIST",[])),'
        '"middleware": list(getattr(s,"MIDDLEWARE",[])),'
        '"static_root": getattr(s,"STATIC_ROOT",""),'
        '"static_dirs": list(getattr(s,"STATICFILES_DIRS",[])),'
        '"db": s.DATABASES["default"].get("NAME",""),'
        '"db_engine": s.DATABASES["default"].get("ENGINE",""),'
        '"survey": bool(getattr(s,"SURVEY_API_KEY",""))'
        '}, ensure_ascii=False, default=str))'
    )
    out = run('settings-audit', [py, '-c', code], platform,
              base_env(platform))
    return json.loads(out.strip().splitlines()[-1])


def preflight(platform, py, origin, url):
    if not os.path.isfile(os.path.join(platform, 'manage.py')):
        say('FAIL', 'platform', 'manage.py 不存在')
        return
    say('PASS', 'platform', platform)

    # check / makemigrations 用临时 settings，避免本地缺 simpleui 等可选 app 误报；
    # 只做静态检查，不连接业务库。
    tmp_check = tempfile.mkdtemp(prefix='smupa-golive-check-')
    try:
        _write_test_settings(tmp_check)
        env_check = base_env(platform, tmp_check)
        env_check['DJANGO_SETTINGS_MODULE'] = 'golive_settings'
        env_check['SMUPA_GOLIVE_TEMP_DB'] = os.path.join(
            tmp_check, 'test.sqlite3')
        run('check', [py, 'manage.py', 'check'], platform, env_check)
        say('PASS', 'django-check', '')
        run('makemigrations', [py, 'manage.py', 'makemigrations',
                               '--check', '--dry-run'], platform, env_check)
        say('PASS', 'no-model-drift', '')
    finally:
        shutil.rmtree(tmp_check, ignore_errors=True)

    cfg = _read_settings(platform, py)
    db_name = cfg.get('db') or ''
    db_engine = cfg.get('db_engine') or ''
    db_missing = ('sqlite3' in db_engine and db_name
                  and not os.path.exists(db_name))

    if db_missing:
        say('SKIP', 'migrations', 'SQLite DB 不存在，已跳过（避免创建空库）')
    else:
        out = run('showmigrations', [py, 'manage.py', 'showmigrations', 'web'],
                  platform, base_env(platform))
        pending = [ln for ln in out.splitlines()
                   if ln.strip().startswith('[ ]')]
        if pending:
            say('FAIL', 'migrations', '有未应用迁移：{}'.format(
                ', '.join(x.strip() for x in pending[:8])))
        else:
            say('PASS', 'migrations', '全部已应用')
    if origin:
        if origin in cfg['cors']:
            say('PASS', 'cors-origin', origin)
        else:
            say('FAIL', 'cors-origin',
                '{} 不在 MEDITATION_CORS_ORIGINS（精确匹配）'.format(origin))
    else:
        say('SKIP', 'cors-origin', '未提供 --origin')

    cutoff = str(cfg.get('cutoff') or '')
    if cutoff:
        import datetime
        try:
            datetime.datetime.strptime(cutoff, '%Y-%m-%d %H:%M')
            say('PASS', 'cutoff-format', cutoff)
        except ValueError:
            say('FAIL', 'cutoff-format',
                '必须为 YYYY-MM-DD HH:MM，当前 {!r}'.format(cutoff))
    else:
        say('SKIP', 'cutoff-format', '未配置 MEDITATION_SLOT_REPAIR_CUTOFF')

    if cfg.get('notice'):
        say('SKIP', 'notice-override',
            '生产配置了 MEDITATION_NOTICE_HTML，新默认须知不会生效')
    else:
        say('PASS', 'notice-override', '未覆盖，使用默认须知')

    static_root = os.path.realpath(cfg.get('static_root') or '')
    static_dirs = [os.path.realpath(x) for x in cfg.get('static_dirs') or []]
    if static_root and static_root in static_dirs:
        # 平台既有配置：生产由 nginx 直接服务静态文件，runserver 才会报错。
        # 本项目原则是“平台原问题只记录不修”，这里不阻断上线检查。
        say('SKIP', 'static-root',
            '平台既有配置冲突（生产 nginx 服务静态文件），仅记录')
    else:
        say('PASS', 'static-root', '未冲突')

    if not cfg.get('survey'):
        say('SKIP', 'survey-key', 'SURVEY_API_KEY 为空，调查导出接口关闭')
    else:
        say('PASS', 'survey-key', '已配置')

    # 后端测试用临时 SQLite，不碰生产库
    tmp = tempfile.mkdtemp(prefix='smupa-golive-test-')
    try:
        _write_test_settings(tmp)
        env = base_env(platform, tmp)
        env['DJANGO_SETTINGS_MODULE'] = 'golive_settings'
        env['SMUPA_GOLIVE_TEMP_DB'] = os.path.join(tmp, 'test.sqlite3')
        out = run('backend-tests',
                  [py, 'manage.py', 'test', 'web', '-v', '1'],
                  platform, env, timeout=900)
        say('PASS', 'backend-tests', 'manage.py test web OK')
    except Exception as exc:
        say('FAIL', 'backend-tests', str(exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if db_missing:
        say('SKIP', 'verify-slots', 'SQLite DB 不存在，已跳过')
    else:
        try:
            out = run('verify-slots',
                      [py, 'manage.py', 'verify_meditation_slots'],
                      platform, base_env(platform))
            say('PASS', 'verify-slots', 'OK')
        except Exception as exc:
            say('FAIL', 'verify-slots', str(exc))


def _write_rehearsal_settings(tmp):
    path = os.path.join(tmp, 'golive_rehearsal_settings.py')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(
            "from gzpt.settings import *  # noqa\n"
            "import os\n"
            "_db = os.path.join(os.path.dirname(__file__), 'rehearsal.sqlite3')\n"
            "DATABASES = {'default': {'ENGINE': "
            "'django.db.backends.sqlite3', 'NAME': _db}}\n"
            "_root = os.path.abspath(os.path.dirname(__file__))\n"
            "if not os.path.abspath(_db).startswith(_root + os.sep):\n"
            "    raise RuntimeError('refusing non-temp DB: ' + _db)\n"
            "CACHES = {'default': {'BACKEND': "
            "'django.core.cache.backends.locmem.LocMemCache'}}\n"
            "EMAIL_BACKEND = "
            "'django.core.mail.backends.locmem.EmailBackend'\n"
            "STATIC_ROOT = os.path.join(os.path.dirname(__file__), "
            "'static_root')\n"
            "DEBUG = False\n"
            "MEDITATION_CLOSED_DATES = []\n"
            "MEDITATION_SLOT_REPAIR_CUTOFF = ''\n"
            "_DROP_APPS = {'simpleui', 'django_celery_results'}\n"
            "INSTALLED_APPS = [a for a in INSTALLED_APPS "
            "if a not in _DROP_APPS]\n"
            "if not SECRET_KEY:\n"
            "    SECRET_KEY = 'golive-temporary-secret'\n"
        )
    return path


def rehearsal(platform, py, workdir):
    tmp = tempfile.mkdtemp(prefix='smupa-golive-rehearsal-', dir=workdir)
    try:
        _write_rehearsal_settings(tmp)
        env = base_env(platform, tmp)
        env['DJANGO_SETTINGS_MODULE'] = 'golive_rehearsal_settings'
        env['SMUPA_GOLIVE_TEMP_DB'] = os.path.join(tmp, 'rehearsal.sqlite3')
        run('rehearsal-migrate', [py, 'manage.py', 'migrate', '--noinput'],
            platform, env)
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'golive_rehearsal.py')
        out = run('rehearsal', [py, script], platform, env, timeout=300)
        say('PASS', 'rehearsal', '合成旧数据 dry-run/apply/幂等 OK')
    except Exception as exc:
        say('FAIL', 'rehearsal', str(exc))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _get(url, origin=None):
    req = urllib.request.Request(url)
    if origin:
        req.add_header('Origin', origin)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode('utf-8', 'replace'), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8', 'replace'), exc.headers


def post_deploy(url, origin):
    import datetime
    base = url.rstrip('/')

    try:
        status, body, _ = _get(base + '/meditation/api/layout/')
        data = json.loads(body).get('data') or {}
        ok = (status == 200 and len(data.get('slots') or []) == 7
              and data.get('seat_count') == 17
              and 'open_weekdays_iso' in data and 'closed_dates' in data)
        say('PASS' if ok else 'FAIL', 'live-layout',
            'status={} slots={}'.format(status, len(data.get('slots') or [])))
    except Exception as exc:
        say('FAIL', 'live-layout', str(exc))

    try:
        status, body, _ = _get(base + '/meditation/api/notice/')
        ok = status == 200 and '09:10' in body and '17:00' in body
        say('PASS' if ok else 'FAIL', 'live-notice', 'status={}'.format(status))
    except Exception as exc:
        say('FAIL', 'live-notice', str(exc))

    today = datetime.date.today()
    d = today
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    try:
        status, body, _ = _get(
            base + '/meditation/api/slots/?date=' + d.isoformat())
        data = json.loads(body)
        ok = status == 200 and data.get('status') and len(
            (data.get('data') or {}).get('per_slot') or []) == 7
        say('PASS' if ok else 'FAIL', 'live-slots-open',
            'date={} status={}'.format(d, status))
    except Exception as exc:
        say('FAIL', 'live-slots-open', str(exc))

    sat = today + datetime.timedelta(days=(5 - today.weekday()) % 7 or 7)
    try:
        status, body, _ = _get(
            base + '/meditation/api/slots/?date=' + sat.isoformat())
        data = json.loads(body)
        ok = data.get('status') is False and 'per_slot' not in (
            data.get('data') or {})
        say('PASS' if ok else 'FAIL', 'live-slots-weekend',
            'date={} status={}'.format(sat, data.get('status')))
    except Exception as exc:
        say('FAIL', 'live-slots-weekend', str(exc))

    if origin:
        try:
            req = urllib.request.Request(
                base + '/meditation/api/submit/', method='OPTIONS')
            req.add_header('Origin', origin)
            req.add_header('Access-Control-Request-Method', 'POST')
            with urllib.request.urlopen(req, timeout=15) as resp:
                acao = resp.headers.get('Access-Control-Allow-Origin')
            ok = acao == origin
            say('PASS' if ok else 'FAIL', 'live-cors',
                'ACAO={!r}'.format(acao))
        except Exception as exc:
            say('FAIL', 'live-cors', str(exc))

    try:
        status, body, _ = _get(base + '/dashboard/')
        ok = status in (200, 301, 302)
        say('PASS' if ok else 'FAIL', 'live-dashboard',
            'status={}'.format(status))
    except Exception as exc:
        say('FAIL', 'live-dashboard', str(exc))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', required=True)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--url', default='')
    parser.add_argument('--origin', default='')
    parser.add_argument('--mode', default='all',
                        choices=['preflight', 'rehearsal', 'post-deploy', 'all'])
    parser.add_argument('--workdir', default='')
    args = parser.parse_args()

    platform = os.path.abspath(args.platform)
    py = os.path.abspath(args.python)
    workdir = os.path.abspath(args.workdir or tempfile.mkdtemp(
        prefix='smupa-golive-'))
    os.makedirs(workdir, exist_ok=True)
    print('platform = {}'.format(platform))
    print('python   = {}'.format(py))
    print('workdir  = {}'.format(workdir))

    if args.mode in ('preflight', 'all'):
        preflight(platform, py, args.origin, args.url)
    if args.mode in ('rehearsal', 'all'):
        rehearsal(platform, py, workdir)
    if args.mode in ('post-deploy', 'all') and args.url:
        post_deploy(args.url, args.origin)

    report = {
        'platform': platform,
        'url': args.url,
        'origin': args.origin,
        'pass': PASS,
        'fail': FAIL,
        'skip': SKIP,
        'ok': not FAIL,
    }
    with open(os.path.join(workdir, 'golive-report.json'), 'w',
              encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('\n通过 {}，失败 {}，跳过 {}'.format(len(PASS), len(FAIL), len(SKIP)))
    for name, detail in FAIL:
        print('  FAIL {}: {}'.format(name, detail))
    print('报告: {}'.format(os.path.join(workdir, 'golive-report.json')))
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
