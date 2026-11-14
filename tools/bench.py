# -*- coding: utf-8 -*-
"""轻量压测：不依赖 Locust，用线程池并发打接口，产出 P50/P95/P99 与 RPS。

用法：
    python tools/bench.py                 # 默认三个读接口、每接口 200 次、20 并发
    python tools/bench.py --n 300 --workers 30 --path "/api/images?per_page=200"

设计说明（面试可讲）：
- 自己启动 SUT（seed 数据 + 动态端口），测完回收，不依赖外部已启动的服务
- 用固定请求数 + 固定并发，算的是「客户端视角的端到端延迟」，含 Flask 处理 + JSON 序列化
- 报 P95 而不是平均值：平均值会被少量极快请求拉低，掩盖长尾
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SUT_APP = ROOT / 'sut' / 'app.py'
DATA_DIR = ROOT / 'sut' / 'data'
CSV_DIR = ROOT / 'sut' / 'csv_data'


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def start_sut(port: int):
    env = os.environ.copy()
    env.update({
        'GUOHUA_DATA_DIR': str(DATA_DIR),
        'GUOHUA_CSV_DIR': str(CSV_DIR),
        'GUOHUA_PORT': str(port),
        'PYTHONIOENCODING': 'utf-8',
        'GUOHUA_CLOUD_BASE': 'http://127.0.0.1:1',  # 压测只打本地接口，云端指向不可达地址
    })
    log = open(ROOT / 'test-output' / 'bench_sut.log', 'wb') if (ROOT / 'test-output').exists() else subprocess.DEVNULL
    proc = subprocess.Popen([sys.executable, str(SUT_APP)], env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    deadline = time.time() + 60
    while time.time() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f'SUT 启动失败（code={proc.returncode}）')
        try:
            if requests.get(f'{base}/api/images', timeout=2).status_code == 200:
                return proc, base
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise SystemExit('SUT 60s 内未就绪')


def one(url: str):
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=15)
        ok = r.status_code == 200
        size = len(r.content)
    except requests.RequestException:
        ok, size = False, 0
    return (time.perf_counter() - t0) * 1000, ok, size


def bench(url: str, n: int, workers: int):
    # 预热 5 次，避免首次导入/缓存影响
    for _ in range(5):
        one(url)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = list(ex.map(one, [url] * n))
    lat = sorted(r[0] for r in rows)
    ok_rate = sum(1 for r in rows if r[1]) / len(rows)
    avg_size = sum(r[2] for r in rows) / len(rows) / 1024
    def pct(p):
        idx = min(len(lat) - 1, int(len(lat) * p))
        return lat[idx]
    return {
        'requests': n,
        'workers': workers,
        'ok_rate': round(ok_rate * 100, 1),
        'avg_ms': round(sum(lat) / len(lat), 1),
        'p50_ms': round(pct(0.50), 1),
        'p95_ms': round(pct(0.95), 1),
        'p99_ms': round(pct(0.99), 1),
        'max_ms': round(lat[-1], 1),
        'rps': round(1000 * len(lat) / sum(lat), 1),
        'avg_kb': round(avg_size, 1),
    }


DEFAULT_PATHS = [
    '/api/images?per_page=50',
    '/api/images_count',
    '/api/stats',
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=200)
    ap.add_argument('--workers', type=int, default=20)
    ap.add_argument('--path', action='append', default=None)
    args = ap.parse_args()
    paths = args.path or DEFAULT_PATHS

    port = free_port()
    proc, base = start_sut(port)
    results = {}
    try:
        print(f'SUT: {base}  (seed 数据, 3 条记录)\n')
        header = f'{"endpoint":<32}{"n":>5}{"并发":>5}{"成功率":>7}{"P50":>8}{"P95":>8}{"P99":>8}{"max":>8}{"RPS":>7}{"响应KB":>7}'
        print(header)
        print('-' * len(header))
        for p in paths:
            r = bench(f'{base}{p}', args.n, args.workers)
            results[p] = r
            print(f'{p:<32}{r["requests"]:>5}{r["workers"]:>5}{r["ok_rate"]:>6}%'
                  f'{r["p50_ms"]:>7}ms{r["p95_ms"]:>7}ms{r["p99_ms"]:>7}ms{r["max_ms"]:>7}ms'
                  f'{r["rps"]:>7}{r["avg_kb"]:>7}')
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    out = ROOT / 'test-output' / 'bench_result.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n结果已保存: {out}')


if __name__ == '__main__':
    main()
