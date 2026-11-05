# -*- coding: utf-8 -*-
"""页面级 E2E 用例（Playwright + Chromium）。

补的是接口测试覆盖不到的那一层：模板是否能真正渲染、前端 JS 是否报错、
页面是否能从接口取到数据并落到 DOM 上。

运行方式：
    python -m pytest -m e2e -q          # 单独跑（默认 addopts 会排除 e2e）

注意：本套用例不依赖外部图片服务，示例种子数据里的图片地址是不可解析的示例域名，
因此图片会加载失败——这属于预期行为，用例只断言页面结构与数据绑定。
"""
import pytest

pytestmark = pytest.mark.e2e

PAGES = [
    ('/', '中国绘画分析系统'),
    ('/shinu', '明清仕女图典藏'),
    ('/human', '人工标注'),
]


@pytest.fixture(scope='session')
def browser():
    """启动一次 Chromium，整个会话复用。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture()
def page(browser):
    """每个用例一个干净的上下文，避免 localStorage / 缓存互相污染。"""
    context = browser.new_context(viewport={'width': 1440, 'height': 900})
    pg = context.new_page()
    pg.set_default_timeout(15000)
    errors = []
    pg.on('pageerror', lambda exc: errors.append(str(exc)))
    pg.errors = errors
    yield pg
    context.close()


@pytest.mark.parametrize('path,expected_title', PAGES)
def test_pages_render(page, base_url, path, expected_title):
    """四个页面都能真正渲染：HTTP 200 + 标题正确 + 无未捕获 JS 异常。"""
    resp = page.goto(f'{base_url}{path}', wait_until='domcontentloaded')
    assert resp is not None and resp.status == 200, f'{path} 返回 {resp and resp.status}'
    assert expected_title in page.title(), f'标题不符: {page.title()!r}'
    assert page.locator('body').inner_text().strip(), '页面内容为空'
    assert not page.errors, f'{path} 有未捕获 JS 异常: {page.errors}'


def test_index_chart_canvas_rendered(page, base_url):
    """首页图表 canvas 有实际尺寸（说明 Chart.js 初始化成功，而非 0x0 空白）。"""
    page.goto(f'{base_url}/', wait_until='domcontentloaded')
    canvas = page.locator('#dynastyChart')
    canvas.wait_for(state='visible')
    box = canvas.bounding_box()
    assert box and box['width'] > 100 and box['height'] > 100, f'canvas 尺寸异常: {box}'


def test_shinu_gallery_populated(page, base_url):
    """仕女图典藏页：从 /api/shinu52 取到 52 条并渲染成卡片。"""
    page.goto(f'{base_url}/shinu', wait_until='domcontentloaded')
    cards = page.locator('#galleryGrid > *')
    page.wait_for_function(
        'document.querySelectorAll("#galleryGrid > *").length > 0', timeout=15000)
    assert cards.count() == 52, f'期望 52 张卡片，实际 {cards.count()}'


def test_human_gallery_populated(page, base_url):
    """人工标注页：有标注数据的图片能被渲染出来。"""
    page.goto(f'{base_url}/human', wait_until='domcontentloaded')
    page.wait_for_function(
        'document.querySelectorAll("#gallery > *").length > 0', timeout=15000)
    assert page.locator('#gallery > *').count() >= 1


def test_shinu_search_filters_gallery(page, base_url):
    """前端搜索交互：输入关键词后卡片数量应收敛（非全量）。"""
    page.goto(f'{base_url}/shinu', wait_until='domcontentloaded')
    page.wait_for_function(
        'document.querySelectorAll("#galleryGrid > *").length > 0', timeout=15000)
    before = page.locator('#galleryGrid > *').count()
    page.fill('#searchInput', '示例仕女图 01')
    page.wait_for_timeout(600)
    after = page.locator('#galleryGrid > *').count()
    assert after < before, f'搜索后数量未收敛: {before} -> {after}'


@pytest.mark.xfail(reason='BUG-D17: images.html 调用未定义的 loadFilterOptions()，页面初始化抛 ReferenceError',
                   strict=False)
def test_images_page_has_no_js_errors(page, base_url):
    """图片查看页加载时不应有未捕获 JS 异常。

    实测两条异常：
    1. `loadFilterOptions is not defined` —— images.html 第 1401 行调用了该函数，
       但整个模板里从未定义它（全文件仅此一处出现）。
    2. `Unexpected token '<'` —— 第 637-644 行的 fetch 直接 .json()，
       接口返回 500 的 HTML 错误页时解析失败（由 D11 触发）。
    """
    page.goto(f'{base_url}/images', wait_until='domcontentloaded')
    page.wait_for_timeout(1500)
    assert not page.errors, f'未捕获 JS 异常: {page.errors}'


@pytest.mark.xfail(reason='BUG-D11 的界面表现：/api/images_count 500 导致筛选计数全部为 0',
                   strict=False)
def test_images_filter_counts_not_all_zero(page, base_url):
    """图片查看页的分类计数应与数据一致。

    该页面通过 /api/images_count 取计数，而该接口在中文 Windows 上因
    GBK 解码缺陷直接 500（见 docs/02-缺陷清单.md D11），于是所有计数停留在 (0)。
    这是一条"缺陷在界面上如何暴露"的用例——CI（UTF-8 环境）上会自动 XPASS。
    """
    page.goto(f'{base_url}/images', wait_until='domcontentloaded')
    page.wait_for_timeout(1500)
    counts = [
        page.locator('#filterFemaleCount').inner_text(),
        page.locator('#filterMaleCount').inner_text(),
        page.locator('#filterMixedCount').inner_text(),
    ]
    assert any(c.strip() not in ('(0)', '0', '') for c in counts), f'计数全为 0: {counts}'
