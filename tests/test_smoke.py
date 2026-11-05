# -*- coding: utf-8 -*-
"""冒烟用例：验证 SUT 可用 + 核心接口契约。

这些用例在 CI 里必须全绿；它们同时承担「回归基线」作用——
任何改动导致这些契约变化，都应在 code review 时被注意到。
"""
import pytest

pytestmark = pytest.mark.smoke


@pytest.mark.parametrize('path', ['/', '/images', '/shinu', '/human'])
def test_page_routes_available(api, path):
    """/  /images  /shinu  /human 四个页面均可访问"""
    r = api.get(f'{api.base_url}{path}')
    assert r.status_code == 200
    assert 'text/html' in r.headers.get('Content-Type', '')


def test_images_list_default_pagination(api):
    """/api/images 默认返回全部分页信息，且 total 覆盖 detection + CIT-only"""
    r = api.get(f'{api.base_url}/api/images')
    assert r.status_code == 200
    body = r.json()
    # seed: detection 2 张 + 仅 CIT 1 张
    assert body['total'] == 3
    assert len(body['items']) == 3
    assert all({'uuid', 'category', 'labels', 'num_detections'} <= set(i) for i in body['items'])


def test_images_list_pagination_boundary(api):
    """正常分页：page=2, per_page=2 应返回第 3 条，且 total 不变"""
    r = api.get(f'{api.base_url}/api/images', params={'page': 2, 'per_page': 2})
    body = r.json()
    assert body['total'] == 3
    assert len(body['items']) == 1


@pytest.mark.parametrize('keyword,expected', [('1111', 1), ('ffff', 0)])
def test_images_uuid_search(api, keyword, expected):
    """/api/images?search= 按 UUID 子串模糊匹配，大小写不敏感"""
    r = api.get(f'{api.base_url}/api/images', params={'search': keyword})
    assert r.json()['total'] == expected


def test_image_detail_full_record(api, seed_ids):
    """/api/image/<uuid> 聚合 pose / detection / cit / dino 四个数据源"""
    r = api.get(f'{api.base_url}/api/image/{seed_ids["full"]}')
    assert r.status_code == 200
    body = r.json()
    assert body['pose'] is not None
    assert body['detection']['num_detections'] == 2
    assert body['cit']['num_detections'] == 2
    assert body['dino']['num_detections'] == 1


def test_image_detail_filters_low_confidence_keypoints(api, seed_ids):
    """业务规则：关键点置信度 <= 0.3 不应返回给前端"""
    body = api.get(f'{api.base_url}/api/image/{seed_ids["full"]}').json()
    confidences = [kp['confidence'] for kp in body['pose']['keypoints']]
    assert confidences, 'seed 数据应含高置信度关键点'
    assert min(confidences) > 0.3
    assert body['pose']['total_keypoints'] == 133


def test_stats_aggregation(api):
    """/api/stats 各维度统计口径一致：分类/朝代/关键点总数"""
    body = api.get(f'{api.base_url}/api/stats').json()
    assert body['total_images'] == 2
    assert sum(body['category_freq'].values()) == 2
    assert body['images_with_pose'] == 2
    assert body['total_high_conf_kp'] == 133 * 2
    assert 0 < body['avg_confidence'] <= 1


def test_filter_options_include_csv_dynasty(api):
    """朝代选项来自 CSV（验证 CSV_DIR 注入生效，同时守护「数据源缺失静默降级」缺陷 D02）"""
    body = api.get(f'{api.base_url}/api/filter_options').json()
    assert '女' in body['categories'] and '男' in body['categories']
    assert '宋代' in body['dynasties'] and '明代' in body['dynasties']
    assert 'objects.fan' in body['cit_labels']


def test_filter_by_category(api):
    """/api/filter 单条件筛选"""
    body = api.get(f'{api.base_url}/api/filter', params={'category': '女'}).json()
    assert body['total'] == 1
    assert body['items'][0]['uuid'].startswith('1111')


def test_filter_multi_condition_is_and(api):
    """多条件之间为 AND 关系"""
    body = api.get(f'{api.base_url}/api/filter',
                   params={'category': '女', 'dynasty': '明代'}).json()
    assert body['total'] == 0


def test_human_annotations_skip_unannotated(api, seed_ids):
    """业务规则：atrID 为空的记录不进入人工标注列表"""
    body = api.get(f'{api.base_url}/api/human_annotations').json()
    assert body['total'] == 1
    assert body['items'][0]['uuid'] == seed_ids['full']
    assert body['items'][0]['num_local'] == 2


def test_human_stats_consistency(api):
    """/api/human_stats 的 total 应与列表接口口径一致"""
    stats = api.get(f'{api.base_url}/api/human_stats').json()
    listed = api.get(f'{api.base_url}/api/human_annotations').json()
    assert stats['total'] == listed['total']
    assert stats['by_user'].get('annotator_a') == 1


def test_human_annotation_detail_404_for_missing(api, seed_ids):
    """正确的 REST 语义：资源不存在返回 404（注意与 D05 形成对比）"""
    r = api.get(f'{api.base_url}/api/human_annotation/{seed_ids["missing"]}')
    assert r.status_code == 404
    assert 'error' in r.json()


def test_shinu52_returns_52_items(api):
    """/api/shinu52 契约：固定 52 张"""
    body = api.get(f'{api.base_url}/api/shinu52').json()
    assert isinstance(body, list) and len(body) == 52
    assert {'id', 'title', 'dynasty', 'keypoints'} <= set(body[0])


def test_mingqing_ids_returns_list(api, seed_ids):
    """/api/mingqing_ids 返回 ID 列表（该文件为纯 ASCII，不受编码缺陷影响）"""
    body = api.get(f'{api.base_url}/api/mingqing_ids').json()
    assert isinstance(body, list)
    assert set(body) == {seed_ids['full'], seed_ids['det_only']}


def test_download_rejects_empty_result(api):
    """下载接口在筛选结果为空时返回 400 + 明确错误信息，不应生成空压缩包"""
    r = api.get(f'{api.base_url}/api/download', params={'dynasty': '不存在的朝代'})
    assert r.status_code == 400
    assert 'error' in r.json()
