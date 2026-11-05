# -*- coding: utf-8 -*-
"""缺陷用例：断言「正确行为」，当前实现不满足 → xfail。

用法的意义：
- 用例表达的是期望契约，不是当前行为，因此缺陷修复后这些用例会自动 XPASS
- CI 保持绿色，同时用 `pytest -rx` 一眼看到未修复缺陷数量
- 每个用例的 reason 直接指向 docs/02-缺陷清单.md 的缺陷编号
"""
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.defect

SUT_APP = Path(__file__).resolve().parent.parent / 'sut' / 'app.py'


@pytest.mark.xfail(reason='BUG-D05: /api/image/<uuid> 不存在时返回 200 + 全 null，应为 404',
                   strict=False)
def test_image_detail_missing_should_404(api, seed_ids):
    """REST 语义：资源不存在应返回 404，而当前实现对任意 uuid 都返回 200。

    对比 /api/human_annotation/<uuid>（会正确返回 404），说明同项目内契约不一致。
    """
    r = api.get(f'{api.base_url}/api/image/{seed_ids["missing"]}')
    assert r.status_code == 404, (
        f'实际 {r.status_code}，响应体 {r.text[:200]}')


@pytest.mark.xfail(reason='BUG-D06: page=0 时按负索引切片，静默返回空列表且不报错',
                   strict=False)
def test_page_zero_should_return_first_page_or_400(api):
    """page 从 0 开始是常见调用错误。合理行为：返回第一页，或参数校验失败 400。

    当前实现 start = (0 - 1) * 10 = -10，切片 items[-10:0] 恒为空列表，
    但 total 仍返回 3 → 前端会显示"有数据但列表为空"。
    """
    body = api.get(f'{api.base_url}/api/images', params={'page': 0, 'per_page': 10}).json()
    assert len(body['items']) > 0 or body.get('total') == 0, (
        f'total={body["total"]} 但 items={len(body["items"])}，分页契约不一致')


@pytest.mark.xfail(reason='BUG-D06: per_page 为负数时切片 list[0:-1] 静默丢弃最后一条',
                   strict=False)
def test_negative_per_page_should_not_silently_drop_items(api):
    """per_page=-1 → end=-1，返回 n-1 条，用户无感知地少了一条数据。"""
    body = api.get(f'{api.base_url}/api/images', params={'page': 1, 'per_page': -1}).json()
    assert len(body['items']) == body['total'], (
        f'total={body["total"]} 但只返回 {len(body["items"])} 条')


@pytest.mark.xfail(reason='BUG-D07: per_page 无上限校验，可一次拉取全量数据',
                   strict=False)
def test_per_page_should_have_upper_bound(api):
    """per_page 未做上限保护，传 1e8 时会把全部数据一次性序列化返回。

    真实数据集 18508 张时，响应体可达数十 MB，属于典型的资源耗尽风险。
    """
    r = api.get(f'{api.base_url}/api/images', params={'per_page': 100000000})
    assert r.status_code == 400, f'实际 {r.status_code}，未拒绝异常 per_page'


@pytest.mark.xfail(reason='BUG-D13: /api/filter 的 cit_label 回退用 detection labels 匹配，标签空间混用导致误命中',
                   strict=False)
def test_filter_cit_label_should_not_match_detection_labels(api):
    """CIT 标签空间是 `objects.fan` 这类层级标签，detection 是 `person`/`fan`。

    app.py 第 864 行：cit_label in item.get('cit_labels', item.get('labels', []))
    对无 CIT 结果的图片回退用 labels 匹配，于是 cit_label=person 会命中纯检测图。
    """
    body = api.get(f'{api.base_url}/api/filter', params={'cit_label': 'person'}).json()
    assert body['total'] == 0, f'误命中 {body["total"]} 条：{[i["uuid"] for i in body["items"]]}'


@pytest.mark.xfail(reason='BUG-D01: 启动提示端口 5001 与实际监听端口 8000 不一致',
                   strict=False)
def test_startup_log_port_matches_actual_port():
    """静态一致性检查：打印给用户的访问地址必须等于 app.run 的实际端口。

    这类「文档/配置漂移」是真实故障来源，可用源码扫描在 CI 中持续守护。
    """
    src = SUT_APP.read_text(encoding='utf-8')
    printed = re.findall(r'http://localhost:(\d+)', src)
    listening = re.findall(r'app\.run\([^)]*port=(\d+)', src)
    assert printed and listening, '未定位到端口声明，检查源码是否变动'
    assert printed[-1] == listening[-1], f'提示端口 {printed[-1]} != 监听端口 {listening[-1]}'


@pytest.mark.xfail(reason='BUG-D11: open() 未指定 encoding，中文 Windows（默认 GBK）下直接 500',
                   strict=False)
def test_images_count_should_not_depend_on_platform_encoding(api):
    """/api/images_count 读取 public_copyright_by_category.json（含中文 key）。

    app.py 第 658 行 open(copyright_file, 'r') 未指定 encoding，
    在 locale=cp936 的 Windows 上抛 UnicodeDecodeError，接口 100% 500。
    在 UTF-8 默认环境的 Linux/CI 上该用例会 XPASS，这正是「跨平台兼容性」测试的价值。
    """
    r = api.get(f'{api.base_url}/api/images_count')
    assert r.status_code == 200, f'实际 {r.status_code}：{r.text[:150]}'


@pytest.mark.xfail(reason='BUG-D11: 同上，含中文 key 的 JSON 读取 500', strict=False)
def test_public_copyright_ids_should_not_depend_on_encoding(api):
    """/api/public_copyright_ids 同样未指定 encoding，见 app.py 第 554 行。"""
    r = api.get(f'{api.base_url}/api/public_copyright_ids')
    assert r.status_code == 200, f'实际 {r.status_code}：{r.text[:150]}'


@pytest.mark.xfail(reason='BUG-D05b: /api/images_count 的 total 与 /api/images 口径应一致，当前因 D11 无法验证',
                   strict=False)
def test_images_count_total_contract(api):
    """口径一致性用例：两个列表类接口的 total 必须相等（D11 修复后可转为冒烟用例）。"""
    count = api.get(f'{api.base_url}/api/images_count').json()
    images = api.get(f'{api.base_url}/api/images').json()
    assert count['total'] == images['total'] == 3

