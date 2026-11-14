# -*- coding: utf-8 -*-
"""云端依赖接口的测试（用本地假云端替代外部对象存储）。

背景：
- SUT 有 4 个路由依赖云端存储：/api/thumb、/api/cloud_url、/images/<path>、/api/scroll
- SUT 是独立子进程，测试进程内的 requests-mock 拦不到它的出站请求
- 解决方式：给 SUT 增加 GUOHUA_CLOUD_BASE 环境变量入口（第 4 处可测性改造），
  测试时指向 tools/fake_cloud.py，用 /__mode 切换"成功 / 500 / 404"分支

覆盖目标：不只看"成功路径"，更要看**第三方失败时接口怎么降级**——
这是线上最容易出问题、也最常被漏测的地方。
"""
import pytest


@pytest.mark.smoke
def test_thumb_success(api, fake_cloud, seed_ids):
    """云端正常时，缩略图接口应返回图片二进制与正确的 Content-Type。"""
    fake_cloud.set_mode('ok')
    r = api.get(f"{api.base_url}/api/thumb/{seed_ids['full']}")
    assert r.status_code == 200
    assert r.headers['Content-Type'].startswith('image/')
    assert len(r.content) > 0


@pytest.mark.smoke
def test_serve_image_success(api, fake_cloud):
    """静态图片路由同样走云端，成功时返回图片。"""
    fake_cloud.set_mode('ok')
    r = api.get(f"{api.base_url}/images/bucket/seed.png")
    assert r.status_code == 200
    assert r.headers['Content-Type'].startswith('image/')


@pytest.mark.smoke
def test_cloud_url_returns_path(api, fake_cloud, seed_ids):
    """cloud_url 接口应返回包含云端路径的 URL 字符串。"""
    fake_cloud.set_mode('ok')
    r = api.get(f"{api.base_url}/api/cloud_url/{seed_ids['full']}")
    assert r.status_code == 200
    assert '/bucket/seed.png' in r.json()['url']


@pytest.mark.smoke
def test_serve_image_cloud_404(api, fake_cloud):
    """云端返回 404 时，接口应返回 404（当前实现符合）。"""
    fake_cloud.set_mode('objects_404')
    r = api.get(f"{api.base_url}/images/bucket/missing.png")
    assert r.status_code == 404


@pytest.mark.defect
@pytest.mark.xfail(reason='BUG-D19: 云端 500 被 except 吞掉并伪装成 404 空响应，'
                          '调用方无法区分"图片不存在"与"云端故障"', strict=False)
def test_thumb_cloud_500_should_not_mask_error(api, fake_cloud, seed_ids):
    """云端 500 时，接口应返回 5xx（或明确错误体），而不是伪装成 404。"""
    fake_cloud.set_mode('objects_500')
    r = api.get(f"{api.base_url}/api/thumb/{seed_ids['full']}")
    assert r.status_code >= 500 or (r.status_code == 200 and r.json().get('error'))


@pytest.mark.defect
@pytest.mark.xfail(reason='BUG-D20: uuid 无法解析时 cloud_url 返回 200 + 空字符串，'
                          '调用方无法区分"没有这张图"与"云端解析失败"', strict=False)
def test_cloud_url_when_resolve_fails_should_signal_error(api, fake_cloud, seed_ids):
    """云端解析失败时，接口应给出可判别的错误，而不是 200 + 空 url。"""
    # 注意：必须用"还没被其他用例解析过"的 uuid。
    # SUT 内部有 image_path_cache，一旦某个 uuid 解析成功就被缓存，
    # 后续用例即使云端故障也会命中缓存——这就是「用例间状态污染」，
    # 会让缺陷被掩盖、症状随执行顺序变化（flaky 的温床）。
    fake_cloud.set_mode('workinfo_500')
    r = api.get(f"{api.base_url}/api/cloud_url/{seed_ids['cit_only']}")
    assert r.status_code >= 400 or r.json().get('url')
