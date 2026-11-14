# -*- coding: utf-8 -*-
"""本地假云端：替代 SUT 依赖的云存储，用于测试第三方依赖的成功/失败分支。

为什么要它：
- SUT 是**独立子进程**，测试进程里的 requests-mock 拦不到它发出的请求
- 所以给 SUT 加了 GUOHUA_CLOUD_BASE 环境变量入口，把云端地址指向本服务
- 本服务通过 /__mode 切换行为：ok / objects_500 / objects_404 / workinfo_500

用法：由 conftest.py 的 fake_cloud fixture 启动，端口通过 FAKE_CLOUD_PORT 传入。
"""
import base64
import os

from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# 1x1 透明 PNG
PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)

STATE = {'mode': 'ok'}


@app.get('/__mode')
def get_mode():
    return jsonify(STATE)


@app.post('/__mode')
def set_mode():
    STATE['mode'] = (request.get_json(silent=True) or {}).get('mode', 'ok')
    return jsonify(STATE)


@app.post('/server/getworkinfobyimageid')
def workinfo():
    """SUT 用它把 uuid 解析成云端图片路径。"""
    if STATE['mode'] == 'workinfo_500':
        return 'workinfo boom', 500
    return jsonify({'success': True, 'content': {'encoding': '/bucket/seed.png'}})


@app.get('/server/getobjects')
def getobjects():
    """SUT 用它拉真实图片二进制。"""
    mode = STATE['mode']
    if mode == 'objects_500':
        return 'objects boom', 500
    if mode == 'objects_404':
        return 'object not found', 404
    return Response(PNG_BYTES, content_type='image/png')


if __name__ == '__main__':
    port = int(os.environ.get('FAKE_CLOUD_PORT', '0'))
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)
