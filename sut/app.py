# ============================================================
# 本文件是某课题组内部 WebUI 的脱敏副本，仅做了 3 处可测性改造
# （DATA_DIR / CSV_DIR / PORT 支持环境变量），业务逻辑未改动；
# 云端服务域名已替换为示例域名，seed 数据为合成数据。
# 缺陷保持原样，见 docs/02-缺陷清单.md
# ============================================================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中国绘画分析WebUI
功能：
1. 首页：统计图表
2. 图片查看：关键点+检测结果开关
"""

import os
import json
import csv
import threading
import requests
from io import BytesIO
from PIL import Image
from flask import Flask, render_template, jsonify, send_from_directory, request, redirect
from collections import Counter

app = Flask(__name__)

# 数据路径（自动适配当前用户家目录）
HOME = os.path.expanduser('~')
DATA_DIR = os.environ.get('GUOHUA_DATA_DIR') or os.path.join(os.path.dirname(__file__), 'data')
IMAGES_DIR = os.path.join(HOME, 'yolo/data/raw/images')
CSV_DIR = os.environ.get('GUOHUA_CSV_DIR') or os.path.join(os.path.dirname(__file__), 'csv_data')

# 云端图片服务
CLOUD_IMAGE_URL = "https://cloud.example.invalid/server/getobjects?bucket=images&path="

# 图片路径缓存
image_path_cache = {}

def get_image_path(uuid):
    """通过API获取正确的图片路径"""
    if uuid in image_path_cache:
        return image_path_cache[uuid]
    try:
        resp = requests.post(
            'https://cloud.example.invalid/server/getworkinfobyimageid',
            json={'imageId': uuid},
            timeout=10,
            verify=False
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success') and data.get('content'):
                encoding = data['content'].get('encoding', '')
                if encoding:
                    image_path_cache[uuid] = encoding
                    return encoding
    except:
        pass
    return None

# 加载数据
print("加载数据...")
with open(os.path.join(DATA_DIR, 'pose_results_all.json'), 'r', encoding='utf-8') as f:
    pose_data = json.load(f)

with open(os.path.join(DATA_DIR, 'merged_results.json'), 'r', encoding='utf-8') as f:
    detection_data = json.load(f)

# 加载CIT检测结果
cit_data = []
cit_path = os.path.join(DATA_DIR, 'cit_results.json')
if os.path.exists(cit_path):
    with open(cit_path, 'r', encoding='utf-8') as f:
        cit_data = json.load(f)
    print("CIT检测数据: {}张".format(len(cit_data)))

# 加载DINO-X原始检测结果
dino_data = []
dino_path = os.path.join(DATA_DIR, 'dino_results.json')
if os.path.exists(dino_path):
    with open(dino_path, 'r', encoding='utf-8') as f:
        dino_data = json.load(f)
    print("DINO检测数据: {}张".format(len(dino_data)))

# 加载人工标注数据
human_ann_data = {}
human_ann_path = os.path.join(DATA_DIR, 'human_annotations.json')
if os.path.exists(human_ann_path):
    with open(human_ann_path, 'r', encoding='utf-8') as f:
        human_ann_data = json.load(f)
    print("人工标注数据: {}张".format(len(human_ann_data)))

# 加载CSV获取朝代信息
dynasty_map = {}
csv_files = ['画作信息_男.csv', '画作信息_女.csv', '画作信息_有男有女.csv', '画作信息_点景人物.csv']
for csv_file in csv_files:
    csv_path = os.path.join(CSV_DIR, csv_file)
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                img_id = row.get('imageID', '')
                dynasty = row.get('dynasty', '')
                if img_id and dynasty:
                    dynasty_map[img_id] = dynasty

print("朝代信息: {}条".format(len(dynasty_map)))

# 建立索引
pose_dict = {item['image_id']: item for item in pose_data}
detection_dict = {item['uuid']: item for item in detection_data}
cit_dict = {item['uuid']: item for item in cit_data}
dino_dict = {item['uuid']: item for item in dino_data}

# 添加朝代信息到detection_dict
for uuid in detection_dict:
    if uuid in dynasty_map:
        detection_dict[uuid]['dynasty'] = dynasty_map[uuid]

print("姿态数据: {}张".format(len(pose_data)))
print("检测数据: {}张".format(len(detection_data)))

@app.route('/')
def index():
    """首页 - 统计概览"""
    return render_template('index.html')

@app.route('/images')
def images_page():
    """图片查看页面"""
    return render_template('images.html')

@app.route('/shinu')
def shinu_page():
    """明清仕女图典藏页面"""
    return render_template('shinu.html')

@app.route('/human')
def human_page():
    """人工标注页面"""
    return render_template('human.html')

@app.route('/api/human_annotations')
def get_human_annotations():
    """返回人工标注图片列表"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    search = request.args.get('search', '', type=str).strip().lower()
    user_filter = request.args.get('user', '', type=str)

    items = []
    for uuid, ann in human_ann_data.items():
        # 跳过没有真标注的
        if not ann.get('atrID'):
            continue

        entry = {
            'uuid': uuid,
            'atrID': ann.get('atrID', ''),
            'date': ann.get('date', ''),
            'user': ann.get('user', ''),
            'global_tags': ann.get('global_tags', {}),
            'num_local': len(ann.get('local_annotations', [])),
            'objects': list(set(obj for a in ann.get('local_annotations', []) for obj in a.get('objects', []))),
            'techniques': list(set(tech for a in ann.get('local_annotations', []) for tech in a.get('techniques', []))),
        }
        items.append(entry)

    # 筛选
    if search:
        items = [i for i in items if search in i['uuid'].lower()]
    if user_filter:
        items = [i for i in items if i['user'] == user_filter]

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page

    return jsonify({'items': items[start:end], 'total': total})

# 云端原图尺寸缓存（进程内），避免重复请求
_cloud_size_cache = {}

def get_cloud_image_size(uuid):
    """从云端API获取原图尺寸 [width, height]（人工标注的坐标空间），带内存缓存"""
    if uuid in _cloud_size_cache:
        return _cloud_size_cache[uuid]
    size = []
    try:
        resp = requests.post(
            'https://cloud.example.invalid/server/getworkinfobyimageid',
            json={'imageId': uuid},
            timeout=5,
            verify=False
        )
        if resp.status_code == 200:
            content = resp.json().get('content', {})
            w = content.get('width')
            h = content.get('height')
            if w and h:
                size = [w, h]
    except Exception:
        pass
    _cloud_size_cache[uuid] = size
    return size


# ==================== 长卷完整图（瓦片拼接） ====================
# 云端对部分超宽长卷只返回截断图（如 API 报 32950x1327，实际图只有 2654x1327），
# 完整画面只存在于瓦片金字塔 tcp03tiles512/<uuid>.jpg/{z}/{x}/{y}.png 中。
# 注意：不能按宽高比猜测是否截断——直接下载云端图，对比 API 报告尺寸与
# 实际尺寸的宽高比：等比缩放=未截断（正常展示），比例变了=被截断（走拼接）。

SCROLL_TILE_URL = "https://cloud.example.invalid/server/getobjects?bucket=images&path=tcp03tiles512/{}.jpg"
SCROLL_CACHE_DIR = os.path.join(DATA_DIR, 'scroll_cache')
_tile_path_cache = {}  # uuid -> tilesPath 或 None


def get_tiles_path(uuid):
    """从云端API获取瓦片金字塔路径 tilesPath（不同图路径不同：tcp01tiles512/*.tif 或 tcp03tiles512/*.jpg）"""
    if uuid in _tile_path_cache:
        return _tile_path_cache[uuid]
    path = None
    try:
        resp = requests.post(
            'https://cloud.example.invalid/server/getworkinfobyimageid',
            json={'imageId': uuid},
            timeout=8, verify=False
        )
        if resp.status_code == 200:
            path = resp.json().get('content', {}).get('tilesPath') or None
    except Exception:
        pass
    _tile_path_cache[uuid] = path
    return path


def get_tile_base_url(uuid):
    """返回该图瓦片金字塔的基础URL，无瓦片返回None"""
    tp = get_tiles_path(uuid)
    if tp:
        return f'https://cloud.example.invalid/server/getobjects?bucket=images&path={tp}'
    return None
_scroll_locks = {}
_scroll_locks_guard = threading.Lock()
# 截断检测缓存: uuid -> bool（是否被截断）
_truncation_cache = {}
# 实际图尺寸缓存: uuid -> (w, h)
_actual_size_cache = {}
# 瓦片存在性缓存: uuid -> bool
_tile_available_cache = {}


def has_tiles(uuid):
    """检测该图是否有瓦片金字塔（缓存，每图只探测一次）"""
    if uuid in _tile_available_cache:
        return _tile_available_cache[uuid]
    available = False
    tile_base = get_tile_base_url(uuid)
    if tile_base:
        try:
            r = requests.get(f'{tile_base}/0/0/0.png', timeout=5, verify=False, stream=True)
            available = r.status_code == 200
        except Exception:
            pass
    _tile_available_cache[uuid] = available
    return available


def detect_truncation(uuid):
    """检测云端返回的图是否被截断，返回 (是否截断, 云端图字节)。

    方法：下载云端图取实际宽高比，与 API 报告的宽高比对比。
    - 比例一致（±5%）→ 只是等比压缩，未截断
    - 比例明显变了 → 被切割，需要瓦片拼接
    检测结果缓存（每张图只下载检测一次）；未截断时字节直接复用给响应。
    """
    cached = _truncation_cache.get(uuid)
    if cached is not None:
        return cached, None

    truncated = False
    content = None
    api_size = get_cloud_image_size(uuid)
    img_path = get_image_path(uuid)
    if api_size and img_path:
        try:
            resp = requests.get(CLOUD_IMAGE_URL + img_path, timeout=15, verify=False)
            if resp.status_code == 200:
                content = resp.content
                w, h = Image.open(BytesIO(content)).size
                _actual_size_cache[uuid] = (w, h)
                api_ratio = api_size[0] / api_size[1]
                actual_ratio = w / h
                # 宽高比变化超过5% → 判定被切割
                if abs(actual_ratio - api_ratio) / api_ratio > 0.05:
                    truncated = True
                    content = None  # 截断图不用于展示
                    app.logger.info(
                        f"图片被切割 {uuid}: API {api_size[0]}x{api_size[1]} "
                        f"(比例{api_ratio:.1f}) vs 实际 {w}x{h} (比例{actual_ratio:.1f})")
        except Exception:
            pass

    _truncation_cache[uuid] = truncated
    return truncated, content


def _get_scroll_lock(uuid):
    with _scroll_locks_guard:
        if uuid not in _scroll_locks:
            _scroll_locks[uuid] = threading.Lock()
        return _scroll_locks[uuid]


def _tile_exists(tile_base, z, x, y):
    try:
        r = requests.get(f'{tile_base}/{z}/{x}/{y}.png', timeout=10, verify=False, stream=True)
        return r.status_code == 200
    except Exception:
        return False


def _probe_grid(tile_base, z):
    """探测某 zoom 层的瓦片网格 (nx, ny)，不存在返回 (0, 0)"""
    if not _tile_exists(tile_base, z, 0, 0):
        return 0, 0

    def max_count(get_coord):
        hi = 1
        while _tile_exists(tile_base, z, *get_coord(hi)):
            hi *= 2
        lo = hi // 2
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if _tile_exists(tile_base, z, *get_coord(mid)):
                lo = mid
            else:
                hi = mid
        return lo + 1

    nx = max_count(lambda i: (i, 0))
    ny = max_count(lambda i: (0, i))
    return nx, ny


def build_scroll_image(uuid, target_width=12000):
    """拼接瓦片生成完整长卷图，返回本地缓存路径。

    从云端API读取 tilesPath 字段获取瓦片路径（不同图路径不同），
    自动选择满足 target_width 的最低 zoom 层（控制请求瓦片数量），
    结果缓存到 data/scroll_cache/<uuid>.jpg。
    """
    tile_base = get_tile_base_url(uuid)
    if not tile_base:
        return None
    os.makedirs(SCROLL_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(SCROLL_CACHE_DIR, f'{uuid}.jpg')
    if os.path.exists(cache_path):
        return cache_path

    # 找最大可用 zoom 及其网格
    zmax = None
    for z in range(0, 10):
        nx, ny = _probe_grid(tile_base, z)
        if nx == 0:
            break
        zmax, gnx, gny = z, nx, ny
    if zmax is None:
        return None

    # 每层网格约翻倍：选覆盖宽度 >= target_width 的最低层
    full_w = gnx * 512  # zmax 层覆盖宽度
    z = zmax
    while z > 0 and full_w / (2 ** (zmax - z + 1)) >= target_width:
        z -= 1
    nx, ny = _probe_grid(tile_base, z)
    if nx == 0:
        return None

    # 拼接
    canvas = Image.new('RGB', (nx * 512, ny * 512), (255, 255, 255))
    for x in range(nx):
        for y in range(ny):
            try:
                r = requests.get(f'{tile_base}/{z}/{x}/{y}.png', timeout=15, verify=False)
                if r.status_code == 200:
                    tile = Image.open(BytesIO(r.content)).convert('RGB')
                    canvas.paste(tile, (x * 512, y * 512))
            except Exception:
                continue

    # 裁掉瓦片取整多出的空白：按API原图尺寸在该zoom下的真实占比裁剪，
    # 保证拼接图比例 = 原图比例，bbox_frac × 画布尺寸 才能画准
    api_size = get_cloud_image_size(uuid)
    if api_size:
        scale = 2 ** z / 2 ** zmax
        crop_w = min(nx * 512, round(api_size[0] * scale))
        crop_h = min(ny * 512, round(api_size[1] * scale))
        if crop_w > 0 and crop_h > 0:
            canvas = canvas.crop((0, 0, crop_w, crop_h))

    canvas.save(cache_path, 'JPEG', quality=88)
    return cache_path


@app.route('/api/scroll/<uuid>')
def get_scroll_image(uuid):
    """完整图：先检测云端图是否被切割，切割过→瓦片拼接完整图，否则直接返回云端原图"""
    from flask import Response
    truncated, content = detect_truncation(uuid)
    if truncated:
        lock = _get_scroll_lock(uuid)
        with lock:
            try:
                path = build_scroll_image(uuid)
                if path:
                    return send_from_directory(SCROLL_CACHE_DIR, f'{uuid}.jpg')
            except Exception as e:
                app.logger.error(f"拼接长卷失败 {uuid}: {e}")
    if content:
        return Response(content, content_type='image/jpeg')
    return get_thumbnail(uuid)


@app.route('/api/human_annotation/<uuid>')
def get_human_annotation_detail(uuid):
    """单张人工标注详情"""
    if uuid not in human_ann_data:
        return jsonify({'error': '未找到'}), 404

    ann = human_ann_data[uuid]

    # 优先从云端API获取原图尺寸——人工标注工具用的就是这个尺寸作为坐标空间。
    # pose/cit/dino 里的 image_size 可能是处理时压缩/截断过的（如手卷宽度被截），
    # 与标注坐标空间不一致，不能用于绘制人工标注框。
    image_size = get_cloud_image_size(uuid)

    # 云端API失败时才用 pose/cit/dino 兜底
    if not image_size:
        if uuid in pose_dict:
            image_size = pose_dict[uuid].get('image_size', [])
        elif uuid in cit_dict:
            image_size = cit_dict[uuid].get('image_size', [])
        elif uuid in dino_dict:
            image_size = dino_dict[uuid].get('image_size', [])

    # 最后兜底：从bbox坐标推算最大值
    if not image_size and ann.get('local_annotations'):
        max_x = max_y = 0
        for local in ann['local_annotations']:
            bbox = local.get('bbox', [])
            if len(bbox) == 4:
                max_x = max(max_x, bbox[2])
                max_y = max(max_y, bbox[3])
        if max_x > 0 and max_y > 0:
            image_size = [max_x, max_y]

    # 检测图片是否被云端切割，并决定标注坐标如何映射
    truncated, _ = detect_truncation(uuid)
    image_truncated = truncated
    local_annotations = ann.get('local_annotations', [])
    display_size = image_size

    if truncated:
        if has_tiles(uuid):
            # 有瓦片：/api/scroll 会拼出完整图，bbox_frac 按原图比例画即可
            pass
        else:
            # 无瓦片：云端只给了裁剪缩略图（如 2896x1448），完整图不存在。
            # 把标注坐标按"缩放"（非裁剪）近似映射到实际显示图尺寸上，
            # 让框在可见画面内大致对齐。
            actual = _actual_size_cache.get(uuid)
            if actual and image_size:
                act_w, act_h = actual
                sx = act_w / image_size[0]
                sy = act_h / image_size[1]
                display_size = [act_w, act_h]
                local_annotations = []
                for la in ann.get('local_annotations', []):
                    bbox = la.get('bbox', [])
                    if len(bbox) == 4:
                        la = dict(la)
                        la['bbox'] = [
                            bbox[0] * sx, bbox[1] * sy,
                            bbox[2] * sx, bbox[3] * sy,
                        ]
                        la['bbox_frac'] = [
                            bbox[0] / image_size[0], bbox[1] / image_size[1],
                            bbox[2] / image_size[0], bbox[3] / image_size[1],
                        ]
                    local_annotations.append(la)

    return jsonify({
        'uuid': uuid,
        'atrID': ann.get('atrID', ''),
        'date': ann.get('date', ''),
        'user': ann.get('user', ''),
        'global_tags': ann.get('global_tags', {}),
        'local_annotations': local_annotations,
        'color_bar': ann.get('color_bar', []),
        'image_size': display_size,
        'image_truncated': image_truncated,
    })

@app.route('/api/human_stats')
def get_human_stats():
    """人工标注统计"""
    from collections import Counter
    user_counter = Counter()
    obj_counter = Counter()
    tech_counter = Counter()
    global_tag_counter = Counter()

    for ann in human_ann_data.values():
        if not ann.get('atrID'):
            continue
        user_counter[ann.get('user', '')] += 1
        for local in ann.get('local_annotations', []):
            obj_counter.update(local.get('objects', []))
            tech_counter.update(local.get('techniques', []))
        for k, v in ann.get('global_tags', {}).items():
            if isinstance(v, list):
                global_tag_counter[f"{k}:{','.join(v)}"] += 1

    return jsonify({
        'total': sum(user_counter.values()),
        'by_user': dict(user_counter.most_common()),
        'top_objects': dict(obj_counter.most_common(20)),
        'top_techniques': dict(tech_counter.most_common(20)),
        'top_global_tags': dict(global_tag_counter.most_common(20)),
    })

@app.route('/api/shinu52')
def get_shinu52():
    """返回52张明清仕女图数据（含检测结果）"""
    data_file = os.path.join(DATA_DIR, 'shinu_52_website.json')
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/api/mingqing_ids')
def get_mingqing_ids():
    """返回明清仕女图ID列表"""
    ids_file = os.path.join(DATA_DIR, 'mingqing_ids.json')
    if os.path.exists(ids_file):
        with open(ids_file, 'r') as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/api/public_copyright_ids')
def get_public_copyright_ids():
    """返回公开版权图片ID列表（按分类）"""
    # 支持按分类查询：?category=男
    category = request.args.get('category')
    ids_file = os.path.join(DATA_DIR, 'public_copyright_by_category.json')
    if os.path.exists(ids_file):
        with open(ids_file, 'r') as f:
            data = json.load(f)
        if category:
            return jsonify(data.get(category, []))
        # 不指定分类时返回所有
        all_ids = []
        for cat_ids in data.values():
            all_ids.extend(cat_ids)
        return jsonify(list(set(all_ids)))
    return jsonify([])

@app.route('/api/stats')
def get_stats():
    """统计数据API"""
    # 物体频率
    label_freq = Counter()
    for item in detection_data:
        for label in item.get('labels', []):
            label_freq[label] += 1

    # 分类分布（女/男/有男有女/点景人物）
    category_freq = Counter()
    for item in detection_data:
        category_freq[item.get('category', '未知')] += 1

    # 朝代分布
    dynasty_freq = Counter()
    for item in detection_data:
        d = item.get('dynasty', '')
        if d:
            dynasty_freq[d] += 1
        else:
            dynasty_freq['未知'] += 1

    # 检测质量指标
    total_confidence = 0
    confidence_count = 0
    total_detections = 0
    images_with_detections = 0
    for item in detection_data:
        detections = item.get('detections', [])
        if detections:
            images_with_detections += 1
            total_detections += len(detections)
            for d in detections:
                c = d.get('confidence', 0)
                if c > 0:
                    total_confidence += c
                    confidence_count += 1

    # 姿态关键点统计
    images_with_pose = len(pose_data)
    total_high_conf_kp = 0
    for item in pose_data:
        kps = item.get('keypoints', [])
        high = sum(1 for kp in kps if len(kp) >= 3 and kp[2] > 0.3)
        total_high_conf_kp += high

    # 各分类的代表性图片（取置信度最高的前4张）
    sample_images = {}
    for item in detection_data:
        cat = item.get('category', '未知')
        if cat not in sample_images:
            sample_images[cat] = []
        detections = item.get('detections', [])
        max_conf = max([d.get('confidence', 0) for d in detections], default=0)
        if len(sample_images[cat]) < 4:
            sample_images[cat].append({
                'uuid': item['uuid'],
                'max_confidence': round(max_conf, 3),
                'labels': item.get('labels', []),
                'dynasty': item.get('dynasty', '')
            })
    # 按置信度排序
    for cat in sample_images:
        sample_images[cat].sort(key=lambda x: x['max_confidence'], reverse=True)

    # 检测结果Top15
    top_labels = label_freq.most_common(15)

    return jsonify({
        'total_images': len(detection_data),
        'category_freq': dict(category_freq.most_common(10)),
        'dynasty_freq': dict(dynasty_freq.most_common(15)),
        'label_freq': dict(top_labels),
        'avg_confidence': round(total_confidence / confidence_count, 3) if confidence_count else 0,
        'avg_detections_per_image': round(total_detections / images_with_detections, 1) if images_with_detections else 0,
        'images_with_detections': images_with_detections,
        'images_with_pose': images_with_pose,
        'total_high_conf_kp': total_high_conf_kp,
        'sample_images': sample_images
    })

@app.route('/api/images_count')
def get_images_count():
    """返回图片真实总数和分类统计"""
    cat_count = Counter()
    for item in detection_dict.values():
        cat_count[item.get('category', '')] += 1

    # 版权统计
    copyright_file = os.path.join(DATA_DIR, 'public_copyright_by_category.json')
    copyright_data = {}
    if os.path.exists(copyright_file):
        with open(copyright_file, 'r') as f:
            copyright_data = json.load(f)
    all_copyright_ids = []
    for ids in copyright_data.values():
        all_copyright_ids.extend(ids)

    # CIT-only图片数
    cit_only = sum(1 for uuid in cit_dict if uuid not in detection_dict)

    return jsonify({
        'total': len(detection_dict) + cit_only,
        'category_count': dict(cat_count),
        'copyright_count': len(set(all_copyright_ids))
    })

@app.route('/api/images')
def get_images():
    """图片列表API - 轻量版，分页返回，支持UUID搜索"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 200, type=int)
    search = request.args.get('search', '', type=str).strip().lower()

    # 合并detection_dict和cit_dict中的所有图片
    all_items = {}
    for uuid, item in detection_dict.items():
        all_items[uuid] = {
            'uuid': uuid,
            'category': item.get('category', ''),
            'labels': item.get('labels', []),
            'num_detections': item.get('num_detections', 0),
            'dynasty': item.get('dynasty', '')
        }
    # 添加仅有CIT数据的图片
    for uuid, item in cit_dict.items():
        if uuid not in all_items:
            all_items[uuid] = {
                'uuid': uuid,
                'category': 'CIT检测',
                'labels': item.get('cit_labels', []),
                'num_detections': item.get('count', 0),
                'dynasty': ''
            }

    all_items_list = list(all_items.values())

    # UUID搜索
    if search:
        all_items_list = [item for item in all_items_list if search in item['uuid'].lower()]

    total = len(all_items_list)
    start = (page - 1) * per_page
    end = start + per_page

    return jsonify({'items': all_items_list[start:end], 'total': total})

@app.route('/api/image/<uuid>')
def get_image_detail(uuid):
    """单张图片详情API"""
    result = {
        'uuid': uuid,
        'pose': None,
        'detection': None,
        'cit': None,
        'dino': None
    }

    if uuid in pose_dict:
        pose_item = pose_dict[uuid]
        # 只返回高置信度的关键点
        keypoints = []
        for kp in pose_item.get('keypoints', []):
            if len(kp) >= 3 and kp[2] > 0.3:
                keypoints.append({'x': kp[0], 'y': kp[1], 'confidence': kp[2]})
        result['pose'] = {
            'keypoints': keypoints,
            'total_keypoints': len(pose_item.get('keypoints', [])),
            'image_size': pose_item.get('image_size', [])
        }

    if uuid in detection_dict:
        det_item = detection_dict[uuid]
        result['detection'] = {
            'labels': det_item.get('labels', []),
            'detections': det_item.get('detections', []),
            'num_detections': det_item.get('num_detections', 0)
        }

    if uuid in cit_dict:
        cit_item = cit_dict[uuid]
        result['cit'] = {
            'detections': cit_item.get('cit_detections', []),
            'labels': cit_item.get('cit_labels', []),
            'num_detections': cit_item.get('count', 0),
            'image_size': cit_item.get('image_size', [])
        }

    if uuid in dino_dict:
        dino_item = dino_dict[uuid]
        result['dino'] = {
            'detections': dino_item.get('dino_detections', []),
            'labels': dino_item.get('dino_labels', []),
            'num_detections': dino_item.get('count', 0),
            'image_size': dino_item.get('image_size', [])
        }

    return jsonify(result)

@app.route('/api/thumb/<uuid>')
def get_thumbnail(uuid):
    """返回图片缩略图 - 通过API获取正确路径"""
    img_path = get_image_path(uuid)
    if img_path:
        cloud_url = CLOUD_IMAGE_URL + img_path
        try:
            resp = requests.get(cloud_url, timeout=10, verify=False)
            if resp.status_code == 200:
                from flask import Response
                return Response(resp.content, content_type=resp.headers.get('Content-Type', 'image/jpeg'))
        except:
            pass
    return '', 404

@app.route('/api/cloud_url/<uuid>')
def get_cloud_url(uuid):
    """返回图片的云端URL"""
    img_path = get_image_path(uuid)
    if img_path:
        return jsonify({'url': CLOUD_IMAGE_URL + img_path})
    return jsonify({'url': ''})

@app.route('/images/<path:filename>')
def serve_image(filename):
    """提供图片文件 - 从云端获取"""
    cloud_url = CLOUD_IMAGE_URL + filename
    try:
        resp = requests.get(cloud_url, timeout=10, verify=False)
        if resp.status_code == 200:
            from flask import Response
            return Response(resp.content, content_type=resp.headers.get('Content-Type', 'image/jpeg'))
    except:
        pass
    return '', 404

@app.route('/api/filter_options')
def get_filter_options():
    """获取筛选选项：CIT标签列表、分类列表、朝代列表"""
    # CIT标签
    cit_labels = set()
    for item in cit_data:
        for label in item.get('cit_labels', []):
            cit_labels.add(label)

    # 分类
    categories = set()
    for item in detection_data:
        categories.add(item.get('category', ''))
    for item in cit_data:
        if item.get('uuid') not in detection_dict:
            categories.add('CIT检测')

    # 朝代
    dynasties = set()
    for d in dynasty_map.values():
        if d:
            dynasties.add(d)

    return jsonify({
        'cit_labels': sorted(cit_labels),
        'categories': sorted(categories),
        'dynasties': sorted(dynasties)
    })

@app.route('/api/filter')
def filter_images():
    """按条件筛选图片"""
    cit_label = request.args.get('cit_label', '')
    category = request.args.get('category', '')
    dynasty = request.args.get('dynasty', '')

    # 合并所有图片
    all_items = {}
    for uuid, item in detection_dict.items():
        all_items[uuid] = {
            'uuid': uuid,
            'category': item.get('category', ''),
            'labels': item.get('labels', []),
            'num_detections': item.get('num_detections', 0),
            'dynasty': item.get('dynasty', '')
        }
    for uuid, item in cit_dict.items():
        if uuid not in all_items:
            all_items[uuid] = {
                'uuid': uuid,
                'category': 'CIT检测',
                'labels': item.get('cit_labels', []),
                'num_detections': item.get('count', 0),
                'dynasty': ''
            }
        else:
            # 合并CIT标签
            all_items[uuid]['cit_labels'] = item.get('cit_labels', [])

    results = list(all_items.values())

    # 筛选CIT标签
    if cit_label:
        results = [item for item in results if cit_label in item.get('cit_labels', item.get('labels', []))]

    # 筛选分类
    if category:
        results = [item for item in results if item.get('category') == category]

    # 筛选朝代
    if dynasty:
        results = [item for item in results if item.get('dynasty') == dynasty]

    return jsonify({'items': results, 'total': len(results)})

@app.route('/api/download')
def download_images():
    """下载筛选后的图片+全部标注数据（打包成zip）"""
    import io
    import zipfile
    from flask import send_file

    cit_label = request.args.get('cit_label', '')
    category = request.args.get('category', '')
    dynasty = request.args.get('dynasty', '')

    # 解析多值参数（逗号分隔）
    cit_labels = [s.strip() for s in cit_label.split(',') if s.strip()] if cit_label else []
    categories = [s.strip() for s in category.split(',') if s.strip()] if category else []
    dynasties = [s.strip() for s in dynasty.split(',') if s.strip()] if dynasty else []

    # 获取筛选结果
    all_items = {}
    for uuid, item in detection_dict.items():
        all_items[uuid] = {
            'uuid': uuid,
            'category': item.get('category', ''),
            'dynasty': item.get('dynasty', '')
        }
    for uuid, item in cit_dict.items():
        if uuid not in all_items:
            all_items[uuid] = {
                'uuid': uuid,
                'category': 'CIT检测',
                'dynasty': ''
            }
        else:
            all_items[uuid]['cit_labels'] = item.get('cit_labels', [])

    results = list(all_items.values())

    if cit_labels:
        results = [item for item in results if any(cl in item.get('cit_labels', []) for cl in cit_labels)]
    if categories:
        results = [item for item in results if item.get('category') in categories]
    if dynasties:
        results = [item for item in results if item.get('dynasty') in dynasties]

    if not results:
        return jsonify({'error': '没有符合条件的图片'}), 400

    # 打包下载（图片 + 标注数据）
    annotations = {}
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for item in results:
            uuid = item['uuid']

            # 收集该图片的所有标注
            ann = {
                'uuid': uuid,
                'category': item.get('category', ''),
                'dynasty': item.get('dynasty', ''),
            }
            if uuid in detection_dict:
                det = detection_dict[uuid]
                ann['detection'] = {
                    'labels': det.get('labels', []),
                    'detections': det.get('detections', []),
                    'num_detections': det.get('num_detections', 0)
                }
            if uuid in cit_dict:
                cit = cit_dict[uuid]
                ann['cit'] = {
                    'detections': cit.get('cit_detections', []),
                    'labels': cit.get('cit_labels', []),
                    'count': cit.get('count', 0),
                    'image_size': cit.get('image_size', [])
                }
            if uuid in dino_dict:
                dino = dino_dict[uuid]
                ann['dino'] = {
                    'detections': dino.get('dino_detections', []),
                    'labels': dino.get('dino_labels', []),
                    'count': dino.get('count', 0),
                    'image_size': dino.get('image_size', [])
                }
            if uuid in pose_dict:
                pose = pose_dict[uuid]
                ann['pose'] = {
                    'keypoints': pose.get('keypoints', []),
                    'total_keypoints': len(pose.get('keypoints', [])),
                    'image_size': pose.get('image_size', [])
                }
            annotations[uuid] = ann

            # 下载原图
            img_path = get_image_path(uuid)
            if img_path:
                cloud_url = CLOUD_IMAGE_URL + img_path
                try:
                    resp = requests.get(cloud_url, timeout=10, verify=False)
                    if resp.status_code == 200:
                        zf.writestr(f"images/{uuid}.jpg", resp.content)
                except:
                    pass

        # 写入标注数据
        zf.writestr('annotations.json', json.dumps(annotations, ensure_ascii=False, indent=2))

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'guohua_export_{len(results)}.zip'
    )

if __name__ == '__main__':
    print("\n启动WebUI...")
    print("访问地址: http://localhost:5001")
    app.run(host='0.0.0.0', port=int(os.environ.get('GUOHUA_PORT', 8000)), debug=False)
