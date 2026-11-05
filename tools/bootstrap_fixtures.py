#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成测试用的种子数据 + 复制并脱敏 SUT（被测系统）app.py。

改造点（共 3 处，全部是为了让系统「可测」）：
1. DATA_DIR 支持环境变量 GUOHUA_DATA_DIR 覆盖  -> 测试用小型 seed 数据，不加载 549MB 真实数据
2. CSV_DIR 支持环境变量 GUOHUA_CSV_DIR 覆盖    -> 原值硬编码为部署机绝对路径，换机器后朝代数据静默为空
3. 端口支持环境变量 GUOHUA_PORT 覆盖            -> 避免与本地已占用端口冲突，支持 CI 并行

另外做两项脱敏：内部云端服务域名替换为示例域名、真实数据集替换为合成数据。
其余业务代码一字未改，缺陷保持原样（这是测试对象，不是修复对象）。
"""
import json
import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_APP = ROOT.parent / 'guohua_webui' / 'app.py'
SUT_DIR = ROOT / 'sut'
DATA_DIR = SUT_DIR / 'data'
CSV_DIR = SUT_DIR / 'csv_data'

U1 = '11111111-1111-4111-8111-111111111111'
U2 = '22222222-2222-4222-8222-222222222222'
U3 = '33333333-3333-4333-8333-333333333333'
MISSING = 'deadbeef-0000-4000-8000-000000000000'

# 按「行首变量名」整体替换，避免把源文件里的部署机绝对路径写进本仓库
LINE_PATCHES = [
    ('DATA_DIR = ',
     "DATA_DIR = os.environ.get('GUOHUA_DATA_DIR') or os.path.join(os.path.dirname(__file__), 'data')"),
    ('CSV_DIR = ',
     "CSV_DIR = os.environ.get('GUOHUA_CSV_DIR') or os.path.join(os.path.dirname(__file__), 'csv_data')"),
]

PATCHES = [
    (
        "app.run(host='0.0.0.0', port=8000, debug=False)",
        "app.run(host='0.0.0.0', port=int(os.environ.get('GUOHUA_PORT', 8000)), debug=False)",
    ),
]


def _replace_line(text: str, prefix: str, new_line: str) -> str:
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    assert len(hits) == 1, f'行锚点异常（命中 {len(hits)} 行）: {prefix}'
    lines[hits[0]] = new_line
    return '\n'.join(lines) + '\n'


def patch_app() -> None:
    text = SRC_APP.read_text(encoding='utf-8')
    for prefix, new_line in LINE_PATCHES:
        text = _replace_line(text, prefix, new_line)
    for old, new in PATCHES:
        assert text.count(old) == 1, f'补丁锚点异常（出现 {text.count(old)} 次）: {old[:60]}'
        text = text.replace(old, new)
    # 脱敏：把内部云端服务域名统一替换为不可解析的示例域名，
    # 避免公开仓库暴露课题组服务地址（用正则而非明文域名，避免仓库里残留原域名）
    text, replaced = re.subn(
        r'https://[A-Za-z0-9.\-]+/server/', 'https://cloud.example.invalid/server/', text
    )
    assert replaced >= 5, f'云端域名脱敏条数异常: {replaced}'
    header = (
        '# ============================================================\n'
        '# 本文件是某课题组内部 WebUI 的脱敏副本，仅做了 3 处可测性改造\n'
        '# （DATA_DIR / CSV_DIR / PORT 支持环境变量），业务逻辑未改动；\n'
        '# 云端服务域名已替换为示例域名，seed 数据为合成数据。\n'
        '# 缺陷保持原样，见 docs/02-缺陷清单.md\n'
        '# ============================================================\n'
    )
    (SUT_DIR / 'app.py').write_text(header + text, encoding='utf-8')


def keypoints(sx: float, sy: float, n: int = 133) -> list:
    """生成 n 个关键点 [x, y, confidence]"""
    out = []
    for i in range(n):
        out.append([round(sx + i, 2), round(sy + i * 0.5, 2), round(0.4 + (i % 6) * 0.1, 3)])
    return out


def write_json(name: str, obj) -> None:
    (DATA_DIR / name).write_text(
        json.dumps(obj, ensure_ascii=False, indent=1), encoding='utf-8'
    )


def build_data() -> None:
    write_json('pose_results_all.json', [
        {'image_id': U1, 'group': 1, 'category': '女',
         'keypoints': keypoints(100, 200), 'image_size': [2048, 1589]},
        {'image_id': U2, 'group': 2, 'category': '男',
         'keypoints': keypoints(300, 400), 'image_size': [1500, 900]},
    ])

    write_json('merged_results.json', [
        {'uuid': U1, 'category': '女', 'group': 1,
         'detections': [
             {'label': 'person', 'confidence': 0.912, 'source': 'dino', 'bbox': [10, 20, 300, 700]},
             {'label': 'fan', 'confidence': 0.51, 'source': 'dino', 'bbox': [320, 410, 420, 500]},
         ],
         'labels': ['person', 'fan'], 'num_detections': 2},
        {'uuid': U2, 'category': '男', 'group': 2,
         'detections': [
             {'label': 'person', 'confidence': 0.655, 'source': 'dino', 'bbox': [5, 6, 100, 400]},
         ],
         'labels': ['person'], 'num_detections': 1},
    ])

    write_json('cit_results.json', [
        {'uuid': U1, 'image_size': [2048, 1589],
         'cit_detections': [
             {'label': 'objects.fan', 'confidence': 0.607, 'bbox': [1040, 694, 1168, 759], 'source': 'dinox'},
             {'label': 'objects.fan', 'confidence': 0.473, 'bbox': [766, 675, 883, 732], 'source': 'dinox'},
         ],
         'cit_labels': ['objects.fan'], 'count': 2},
        {'uuid': U3, 'image_size': [2048, 1589],
         'cit_detections': [
             {'label': 'plants.other_tree', 'confidence': 0.508, 'bbox': [859, 428, 1087, 739], 'source': 'dinox'},
         ],
         'cit_labels': ['plants.other_tree'], 'count': 1},
    ])

    write_json('dino_results.json', [
        {'uuid': U1, 'image_size': [2048, 1589],
         'dino_detections': [
             {'label': 'umbrella', 'confidence': 0.607, 'bbox': [1040, 694, 1168, 759], 'source': 'dinox'},
         ],
         'dino_labels': ['umbrella'], 'count': 1},
    ])

    write_json('human_annotations.json', {
        U1: {
            'atrID': 'ATR0001', 'date': '2022-11-16',
            'user': 'annotator_a',
            'global_tags': {'画意': ['闲适'], '构图': ['立轴']},
            'local_annotations': [
                {'areaId': 1, 'bbox': [870, 302, 1380, 916], 'objects': ['仕女'], 'techniques': ['白描'],
                 'bbox_frac': [0.42, 0.19, 0.67, 0.58]},
                {'areaId': 2, 'bbox': [1040, 822, 1452, 1962], 'objects': ['仕女'], 'techniques': ['设色'],
                 'bbox_frac': [0.51, 0.52, 0.71, 0.83]},
            ],
            'color_bar': [],
        },
        U2: {
            'atrID': '', 'date': '', 'user': 'annotator_b',
            'global_tags': {}, 'local_annotations': [], 'color_bar': [],
        },
    })

    # 明清仕女图 ID 列表（原接口用 open() 未指定 encoding，见 D11；此处按真实数据用纯 ASCII UUID）
    write_json('mingqing_ids.json', [U1, U2])

    # 全部换成合成数据：真实数据属于课题组整理成果，不随公开仓库分发
    write_json('shinu_52_website.json', _synthetic_shinu52())
    write_json('public_copyright_by_category.json', {
        '男': [U2, '44444444-4444-4444-8444-444444444444'],
        '女': [U1, '55555555-5555-4555-8555-555555555555'],
        '点景人物': [U3],
        '有男有女': ['66666666-6666-4666-8666-666666666666'],
    })
    write_json('image_size_cache.json', {
        U1: [2048, 1589],
        U2: [1500, 900],
        U3: [3010, 720],
    })


def _synthetic_shinu52() -> list:
    """52 条合成仕女图数据，字段结构与真实接口一致，内容为占位符。"""
    dynasties = ['明代', '清代', '宋代']
    items = []
    for i in range(52):
        items.append({
            'id': f'00000000-0000-4000-8000-{i:012d}',
            'title': f'示例仕女图 {i + 1:02d}',
            'author': '佚名',
            'dynasty': dynasties[i % len(dynasties)],
            'institution': '示例博物馆',
            'copyright': '是',
            'labels': ['person', 'fan'] if i % 3 else ['person'],
            'num_persons': 1 + i % 3,
            'persons': [],
            'thumbnail_url': f'https://cloud.example.invalid/thumb/{i}.jpg',
            'keypoints': keypoints(50 + i, 80 + i),
            'total_keypoints': 133,
            'high_confidence_keypoints': 90 + i % 40,
            'image_size': [2048, 1589],
        })
    return items


def build_csv() -> None:
    header = 'imageID,dynasty,category,title\n'
    rows = {
        '画作信息_男.csv': f'{U2},明代,男,test_male\n',
        '画作信息_女.csv': f'{U1},宋代,女,test_female\n',
        '画作信息_有男有女.csv': f'{U1},宋代,有男有女,test_mixed\n',
        '画作信息_点景人物.csv': f'{U3},清代,点景人物,test_scene\n',
    }
    for name, body in rows.items():
        # 注意：app.py 用 utf-8-sig 读，因此写 BOM 才与原逻辑一致
        (CSV_DIR / name).write_text(header + body, encoding='utf-8-sig')


def sync_templates() -> None:
    """同步 Jinja 模板目录到 SUT 副本（Flask(__name__) 默认从 app.py 同级 templates/ 渲染）。

    注意排除 templates/app.py：原项目里存在一份与主 app.py 高度重复的快照文件，
    属于配置漂移风险，不作为 SUT 的一部分。
    """
    src = SRC_APP.parent / 'templates'
    dst = SUT_DIR / 'templates'
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('app.py', '__pycache__', '*.bak'))


def main() -> None:
    (SUT_DIR / 'data').mkdir(parents=True, exist_ok=True)
    (SUT_DIR / 'csv_data').mkdir(parents=True, exist_ok=True)
    patch_app()
    sync_templates()
    build_data()
    build_csv()
    print('SUT 就绪:', SUT_DIR / 'app.py')
    print('seed 数据:', sorted(p.name for p in DATA_DIR.iterdir()))
    print('seed CSV:', sorted(p.name for p in CSV_DIR.iterdir()))
    print('templates:', sorted(p.name for p in (SUT_DIR / 'templates').iterdir()))


if __name__ == '__main__':
    main()
