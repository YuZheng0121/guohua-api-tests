# -*- coding: utf-8 -*-
"""pytest 全局配置：启动被测系统（SUT）、提供 HTTP 客户端。

设计要点（面试可讲）：
1. session 级 fixture 只启动一次 SUT，避免每个用例重复启动
2. 通过环境变量注入 seed 数据目录，测试不依赖 549MB 真实数据，CI 秒级启动
3. 端口动态选取空闲端口，不会与其他进程/并行任务冲突
4. 就绪探测用轮询而不是固定 sleep，避免 flaky
5. 启动失败时也保证子进程被回收（否则会泄漏成僵尸监听进程）
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent
SUT_APP = ROOT / 'sut' / 'app.py'
DATA_DIR = ROOT / 'sut' / 'data'
CSV_DIR = ROOT / 'sut' / 'csv_data'
LOG_DIR = ROOT / 'test-output'
SUT_LOG = LOG_DIR / 'sut.log'
READY_TIMEOUT = 60


def _sut_log_tail(lines: int = 40) -> str:
    if not SUT_LOG.exists():
        return '(无日志)'
    text = SUT_LOG.read_text(encoding='utf-8', errors='replace').splitlines()
    return '\n'.join(text[-lines:])


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _terminate(proc: subprocess.Popen) -> None:
    """确保子进程退出，Windows 上没有 SIGKILL 语义，用 terminate + kill 兜底。"""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _wait_ready(proc: subprocess.Popen, base_url: str) -> None:
    deadline = time.time() + READY_TIMEOUT
    last_err = None
    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.fail(f'SUT 进程提前退出（code={proc.returncode}）:\n{_sut_log_tail()}')
        try:
            # 用 /api/images 探测：不读含中文的 JSON，不受 BUG-D11 影响
            if requests.get(f'{base_url}/api/images', timeout=2).status_code == 200:
                return
        except requests.RequestException as exc:
            last_err = exc
        time.sleep(0.25)
    pytest.fail(f'SUT 在 {READY_TIMEOUT}s 内未就绪: {last_err}\n--- SUT 日志 ---\n{_sut_log_tail()}')


@pytest.fixture(scope='session')
def base_url():
    """启动 SUT 子进程（独立端口 + seed 数据），返回 base_url。

    注意：SUT 的 stdout/stderr 必须重定向到文件而不是 subprocess.PIPE。
    用 PIPE 且不读取时，500 的 traceback 会把管道缓冲区写满，
    被测服务随即阻塞在 write 上，表现为「所有请求无响应」的假死。
    这是测试框架自身的经典缺陷，第一次跑就踩到了。
    """
    port = _free_port()
    base = f'http://127.0.0.1:{port}'
    env = os.environ.copy()
    env.update({
        'GUOHUA_DATA_DIR': str(DATA_DIR),
        'GUOHUA_CSV_DIR': str(CSV_DIR),
        'GUOHUA_PORT': str(port),
        'PYTHONIOENCODING': 'utf-8',
    })
    LOG_DIR.mkdir(exist_ok=True)
    if SUT_LOG.exists():
        SUT_LOG.unlink()
    log_fh = open(SUT_LOG, 'wb')
    proc = subprocess.Popen(
        [sys.executable, str(SUT_APP)],
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_ready(proc, base)
    except BaseException:
        _terminate(proc)
        log_fh.close()
        raise
    yield base
    _terminate(proc)
    log_fh.close()


@pytest.fixture(scope='session')
def api(base_url):
    """带 base_url 的 HTTP 会话，连接复用。"""
    session = requests.Session()
    session.base_url = base_url
    yield session
    session.close()


@pytest.fixture(scope='session')
def seed_ids():
    """seed 数据中的固定 ID，避免用例散落魔法值。"""
    return {
        'full': '11111111-1111-4111-8111-111111111111',      # pose + detection + cit + 人工标注
        'det_only': '22222222-2222-4222-8222-222222222222',   # 仅 detection
        'cit_only': '33333333-3333-4333-8333-333333333333',   # 仅 CIT
        'missing': 'deadbeef-0000-4000-8000-000000000000',    # 所有数据源都不存在
    }
