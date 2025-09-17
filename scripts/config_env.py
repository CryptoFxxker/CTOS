#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path
from getpass import getpass

# ---------------- i18n ----------------
LANG = 'zh'  # 'zh' or 'en'

MESSAGES = {
    'choose_language': {
        'zh': '选择语言 / Choose language: 1) 中文  2) English',
        'en': 'Choose language: 1) 中文  2) English',
    },
    'language_set': {
        'zh': '已切换语言为: {lang}',
        'en': 'Language set to: {lang}',
    },
    'project_root': {
        'zh': '项目根目录: {root}',
        'en': 'Project root: {root}',
    },
    'env_file': {
        'zh': '环境文件: {path} (不存在将创建)',
        'en': 'Env file: {path} (will be created if missing)',
    },
    'select_exchanges': {
        'zh': '请选择需要配置的交易所:',
        'en': 'Select exchanges to configure:',
    },
    'select_prompt': {
        'zh': '请选择数字(可用逗号分隔): ',
        'en': 'Enter number(s), comma-separated: ',
    },
    'no_selection': {
        'zh': '未选择任何交易所，退出。',
        'en': 'No exchange selected. Exit.',
    },
    'section_okx': {
        'zh': '\n== 配置 OKX 相关环境变量 ==',
        'en': '\n== Configure OKX environment variables ==',
    },
    'section_bp': {
        'zh': '\n== 配置 Backpack 相关环境变量 ==',
        'en': '\n== Configure Backpack environment variables ==',
    },
    'prefix_prompt': {
        'zh': '为该交易所设置环境变量前缀(默认 {default}_ ): ',
        'en': 'Set env var prefix for this exchange (default {default}_ ): ',
    },
    'current_key': {
        'zh': '当前 {key}: {shown}',
        'en': 'Current {key}: {shown}',
    },
    'keep_current': {
        'zh': '保持当前值? [Y/n]: ',
        'en': 'Keep current value? [Y/n]: ',
    },
    'enter_new_secret': {
        'zh': '请输入新的 {key}: ',
        'en': 'Enter new {key}: ',
    },
    'confirm_new_secret': {
        'zh': '请再次确认 {key}: ',
        'en': 'Confirm {key}: ',
    },
    'mismatch': {
        'zh': '两次输入不一致，请重试。',
        'en': 'Inputs do not match. Please retry.',
    },
    'enter_new_plain': {
        'zh': '请输入新的 {key}: ',
        'en': 'Enter new {key}: ',
    },
    'written': {
        'zh': '已写入 {path}',
        'en': 'Written to {path}',
    },
    'write_failed': {
        'zh': '写入 {path} 失败: {err}',
        'en': 'Failed to write {path}: {err}',
    },
    'final_hint': {
        'zh': '完成。请复制并执行如下命令，以确认将密钥导入环境变量',
        'en': 'Done. Run the following to load env vars into your shell',
    },
}


def t(key: str, **kwargs) -> str:
    variant = MESSAGES.get(key, {})
    msg = variant.get(LANG) or variant.get('en') or ''
    try:
        return msg.format(**kwargs)
    except Exception:
        return msg


def choose_language():
    global LANG
    print(t('choose_language'))
    ans = input('> ').strip()
    if ans == '2':
        LANG = 'en'
    else:
        LANG = 'zh'
    print(t('language_set', lang=('中文' if LANG == 'zh' else 'English')))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_env_lines(env_path: Path):
    if not env_path.exists():
        return []
    try:
        return env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []


def parse_kv_from_line(line: str):
    if not line or line.strip().startswith("#"):
        return None, None
    if "=" not in line:
        return None, None
    key, value = line.split("=", 1)
    return key.strip(), value


def env_to_map(lines):
    kv = {}
    for idx, line in enumerate(lines):
        k, v = parse_kv_from_line(line)
        if k:
            kv[k] = (idx, v)
    return kv


def mask_value(val: str):
    if val is None:
        return ""
    v = val.strip()
    if len(v) <= 4:
        return "*" * len(v)
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


def prompt_choice(prompt: str, choices: list, multi: bool = True):
    print(prompt)
    for i, c in enumerate(choices, 1):
        print(f"  {i}) {c}")
    raw = input(t('select_prompt')).strip()
    if not multi:
        try:
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return [choices[idx - 1]]
        except Exception:
            return []
    selected = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        try:
            idx = int(part)
            if 1 <= idx <= len(choices):
                selected.append(choices[idx - 1])
        except Exception:
            continue
    return list(dict.fromkeys(selected))


def ask_update(key: str, existing: str, secret: bool = True):
    shown = mask_value(existing) if existing is not None else ("(无)" if LANG == 'zh' else "(none)")
    print(t('current_key', key=key, shown=shown))
    ans = input(t('keep_current')).strip().lower()
    if ans in ("", "y", "yes"):  # keep
        return existing
    # set new value
    if secret:
        while True:
            v1 = getpass(t('enter_new_secret', key=key))
            v2 = getpass(t('confirm_new_secret', key=key))
            if v1 == v2:
                return v1
            print(t('mismatch'))
    else:
        return input(t('enter_new_plain', key=key))


def ensure_prefix(default_prefix: str):
    raw = input(t('prefix_prompt', default=default_prefix)).strip().upper()
    if not raw:
        return default_prefix
    return raw.rstrip('_')


def upsert_env(lines: list, kv_map: dict, key: str, new_value: str) -> list:
    line_text = f"{key}={new_value}"
    if key in kv_map:
        idx, _ = kv_map[key]
        lines[idx] = line_text
    else:
        if lines and not lines[-1].endswith("\n"):
            lines.append(line_text)
        else:
            lines.append(line_text)
    return lines


def configure_okx(lines):
    kv = env_to_map(lines)
    prefix = ensure_prefix("OKX")
    keys = [
        f"{prefix}_ACCESS_KEY",
        f"{prefix}_SECRET_KEY",
        f"{prefix}_PASSPHRASE",
    ]
    updated = lines[:]
    for k in keys:
        existing = kv.get(k, (None, None))[1]
        new_val = ask_update(k, existing, secret=True)
        kv = env_to_map(updated)
        updated = upsert_env(updated, kv, k, new_val)
    return updated


def configure_backpack(lines):
    kv = env_to_map(lines)
    prefix = ensure_prefix("BP")
    keys = [
        f"{prefix}_PUBLIC_KEY",
        f"{prefix}_SECRET_KEY",
    ]
    updated = lines[:]
    for k in keys:
        existing = kv.get(k, (None, None))[1]
        new_val = ask_update(k, existing, secret=True)
        kv = env_to_map(updated)
        updated = upsert_env(updated, kv, k, new_val)
    return updated


def main():
    root = project_root()
    env_path = root / ".env"
    print(t('project_root', root=root))
    print(t('env_file', path=env_path))

    lines = load_env_lines(env_path)

    choices = ["OKX", "Backpack"]
    selected = prompt_choice(t('select_exchanges'), choices, multi=True)
    if not selected:
        print(t('no_selection'))
        return 0

    updated = lines[:]
    if "OKX" in selected:
        print(t('section_okx'))
        updated = configure_okx(updated)
    if "Backpack" in selected:
        print(t('section_bp'))
        updated = configure_backpack(updated)

    # 写回 .env
    try:
        env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
        print(t('written', path=env_path))
    except Exception as e:
        print(t('write_failed', path=env_path, err=e))
        return 1

    print(t('final_hint'))
    print(f"echo 'set -a; [ -f {env_path} ] && source {env_path}; set +a' >> ~/.bashrc")
    print("source ~/.bashrc")
    return 0


if __name__ == "__main__":
    choose_language()
    sys.exit(main())


