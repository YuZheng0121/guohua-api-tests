# -*- coding: utf-8 -*-
"""本地假云端：替代 SUT 依赖的云存储，用于测试第三方依赖的成功/失败分支。

为什么要它：
- SUT 是**独立子进程**，测试进程里的 requests-mock 拦不到它发出的请求
- 所以给 SUT 加了 GUOHUA_CLOUD_BASE 环境变量入口，把云端地址指向本服务
- 本服务通过 /__mode 切换行为

支持的模式：
- ok                正常：解析成功、图片可拉
- objects_404       图片不存在
- objects_500       图片服务 500
- workinfo_500      解析接口 500
- scroll_ok         长卷场景：API 报 10000x1000、实际图 1x1（比例不符→判定被切割）→ 走瓦片拼接；瓦片网格 2x1 齐全
- scroll_tile_404   同上，但缺 (1,0) 这块瓦片 → 观察「部分瓦片失败」时的行为

用法：由 conftest.py 的 fake_cloud fixture 启动，端口通过 FAKE_CLOUD_PORT 传入。
"""
import base64
import os

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# 1x1 透明 PNG：用作「被截断」的原图（宽高比 1:1，与 API 报的 10:1 不符）
SMALL_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)

# 512x512 纯色 PNG（瓦片尺寸必须与 SUT 拼接假设一致）
try:
    from io import BytesIO

    from PIL import Image

    _buf = BytesIO()
    Image.new('RGB', (512, 512), (200, 180, 160)).save(_buf, format='PNG')
    TILE_PNG = _buf.getvalue()
except Exception:  # pragma: no cover
    TILE_PNG = SMALL_PNG

STATE = {'mode': 'ok'}

SCROLL_MODES = {'scroll_ok', 'scroll_tile_404'}


def _is_scroll_mode() -> bool:
    return STATE['mode'] in SCROLL_MODES


@app.get('/__mode')
def get_mode():
    return jsonify(STATE)


@app.post('/__mode')
def set_mode():
    STATE['mode'] = (request.get_json(silent=True) or {}).get('mode', 'ok')
    return jsonify(STATE)


@app.post('/server/getworkinfobyimageid')
def workinfo():
    """SUT 用它把 uuid 解析成云端图片路径 / 尺寸 / 瓦片路径。"""
    mode = STATE['mode']
    if mode == 'workinfo_500':
        return 'workinfo boom', 500
    if _is_scroll_mode():
        return jsonify({'success': True, 'content': {
            'width': 10000, 'height': 1000,
            'encoding': '/bucket/truncated.png',
            'tilesPath': '/tiles/seed-longscroll',
        }})
    return jsonify({'success': True, 'content': {'encoding': '/bucket/seed.png'}})


def _tile_ok(x: int, y: int) -> bool:
    if not (0 <= y <= 0):
        return False
    if STATE['mode'] == 'scroll_tile_404':
        return x == 0          # 缺 (1,0)：制造「部分瓦片失败」
    return 0 <= x <= 1         # scroll_ok：2x1 网格齐全


@app.get('/server/getobjects')
def getobjects():
    """SUT 用它拉图片二进制，或拉瓦片 z/x/y.png。"""
    mode = STATE['mode']
    if mode == 'objects_500':
        return 'objects boom', 500
    if mode == 'objects_404':
        return 'object not found', 404

    path = request.args.get('path', '')
    if '/tiles/' in path or path.startswith('tiles/'):
        parts = path.strip('/').split('/')
        try:
            y = int(parts[-1].split('.')[0])
            x = int(parts[-2])
            int(parts[-3])  # z 仅校验格式
        except (ValueError, IndexError):
            return 'bad tile path', 400
        if _tile_ok(x, y):
            return Response(TILE_PNG, content_type='image/png')
        return 'tile not found', 404

    return Response(SMALL_PNG, content_type='image/png')


if __name__ == '__main__':
    port = int(os.environ.get('FAKE_CLOUD_PORT', '0'))
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
