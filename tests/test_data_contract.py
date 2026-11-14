# -*- coding: utf-8 -*-
"""数据契约测试：分类/版权统计的口径一致性。

这几条用例的共同点：**接口自己返回的数据看起来是自洽的**，
只有拿"权威数据源"（CSV、种子数据集）去对账，才能发现不一致。

对应缺陷：
- D23: category 维度混入数据来源伪值「CIT检测」，且 CSV 的多标签被压平成单值
- D24: 公开版权数与总图片数来自不同数据源 → 公开数 > 总数，前端算出负数「非公开 -3」
"""
import pytest

# CSV 里的权威分类（画作信息_{男,女,有男有女,点景人物}.csv）
CATEGORIES_FROM_CSV = {'男', '女', '有男有女', '点景人物'}

# CSV 里的权威归属：uuid 前缀 -> 所属分类集合
# 1111 同时出现在 女.csv 和 有男有女.csv（多标签）
CSV_MEMBERSHIP = {
    '11111111': {'女', '有男有女'},
    '22222222': {'男'},
    '33333333': {'点景人物'},
}


@pytest.mark.defect
@pytest.mark.xfail(reason='BUG-D23: /api/filter_options 的分类来自 detection 数据而非 CSV：'
                          '缺「有男有女」「点景人物」，还混入伪分类「CIT检测」', strict=False)
def test_filter_options_categories_should_come_from_csv(api):
    """分类选项应与 CSV 权威分类一致（业务的分类是 4 个，不含 CIT检测）。"""
    r = api.get(f'{api.base_url}/api/filter_options')
    assert r.status_code == 200
    got = set(r.json()['categories'])
    assert got == CATEGORIES_FROM_CSV


@pytest.mark.defect
@pytest.mark.xfail(reason='BUG-D23: /api/filter 用 detection 的单值 category 精确匹配，'
                          'CSV 中属于「有男有女」「点景人物」的图永远筛不到（静默漏数据）', strict=False)
@pytest.mark.parametrize('category', ['有男有女', '点景人物'])
def test_filter_by_category_should_match_csv_membership(api, category):
    """按分类筛选时，CSV 中属于该分类的图必须被筛出来。"""
    r = api.get(f'{api.base_url}/api/filter', params={'category': category})
    assert r.status_code == 200
    total = r.json()['total']
    expected = sum(1 for cats in CSV_MEMBERSHIP.values() if category in cats)
    assert total == expected, f'分类 {category} 期望 {expected} 条（按 CSV），实际 {total} 条'


@pytest.mark.defect
@pytest.mark.xfail(reason='BUG-D24: 公开版权数来自全量版权清单，总数来自当前数据集，'
                          '两个口径不同源 → 公开数(6) > 总数(3)，前端算出「非公开 -3」', strict=False)
def test_copyright_count_should_not_exceed_total(api):
    """公开版权数不可能超过总图片数。"""
    r = api.get(f'{api.base_url}/api/images_count')
    assert r.status_code == 200
    data = r.json()
    assert data['copyright_count'] <= data['total'], (
        f"copyright_count={data['copyright_count']} > total={data['total']}"
    )


@pytest.mark.defect
@pytest.mark.xfail(reason='BUG-D24: /api/public_copyright_ids 返回 6 条 ID，'
                          '其中 4 条不在当前数据集（共 3 条），跨数据源未校验包含关系', strict=False)
def test_public_copyright_ids_should_subset_dataset(api):
    """公开版权 ID 必须是当前数据集的子集。"""
    ids = api.get(f'{api.base_url}/api/public_copyright_ids').json()
    items = api.get(f'{api.base_url}/api/images', params={'per_page': 100}).json()['items']
    dataset = {i['uuid'] for i in items}
    assert set(ids) <= dataset, f'多出 {sorted(set(ids) - dataset)}'
