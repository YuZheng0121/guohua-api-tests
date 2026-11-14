# 国画分析 WebUI 接口自动化测试

[![api-tests](https://github.com/YuZheng0121/guohua-api-tests/actions/workflows/api-test.yml/badge.svg)](https://github.com/YuZheng0121/guohua-api-tests/actions/workflows/api-test.yml)

对一个真实 Flask 项目的接口层与页面层做自动化测试与缺陷挖掘：**21 个路由、44 条用例、发现 10 个已复现缺陷**，CI 双 Python 版本矩阵 + 独立 E2E job，全部通过。

被测系统（SUT）是一个真实的课题组内部 WebUI（992 行，中国绘画关键点/检测结果可视化），脱敏副本见 [`sut/app.py`](sut/app.py)。测试过程中对 SUT 只做了 3 处**可测性改造**（数据目录 / CSV 目录 / 端口支持环境变量），业务逻辑一行没改——缺陷保持原样，因为它才是测试对象。

## 快速开始

```bash
pip install -r requirements.txt
python -m pytest -qrx
```

预期结果：`24 passed, 9 deselected, 8 xfailed, 3 xpassed in ~4s`

（`9 deselected` 是被 `-m "not e2e"` 排除的页面级 E2E 用例，属正常。）

```bash
python -m playwright install chromium
python -m pytest -q -m e2e -rx
```

预期结果：`7 passed, 2 xfailed`。

> ⚠️ Windows `cmd.exe` 不把 `#` 当注释符。复制命令时不要连同后面的说明一起复制，否则 `#` 会被当成参数传给程序。

`xfailed` 不是失败，而是**已知未修复缺陷**：用例断言的是"正确契约"，当前实现不满足，因此预期失败；缺陷修复后它们会自动变成 XPASS，CI 保持绿色同时不掩盖问题。

生成 HTML 报告：

```bash
python -m pytest --html=test-output/report.html --self-contained-html
```

## 目录结构

```
guohua-api-tests/
├─ sut/                        # 被测系统副本（业务代码未改动）+ seed 数据 + 模板
│  ├─ app.py                   # 原始 app.py，仅 3 处可测性改造
│  ├─ data/                    # 小型 seed 数据（替代 549MB 真实数据）
│  ├─ csv_data/                # 朝代信息 CSV
│  └─ templates/
├─ conftest.py                 # SUT 生命周期、HTTP 会话、固定 ID fixture
├─ tests/
│  ├─ test_smoke.py            # 20 条冒烟/契约用例（必须全绿）
│  ├─ test_defects.py          # 9 条接口缺陷用例（xfail，表达正确契约）
│  └─ test_e2e_pages.py        # 9 条页面级 E2E（Playwright + Chromium）
├─ tools/bootstrap_fixtures.py # 从原项目重建 SUT 副本与 seed 数据
├─ docs/
│  ├─ 01-接口清单与用例设计.md
│  └─ 02-缺陷清单.md
└─ .github/workflows/api-test.yml   # 接口矩阵（3.11/3.13）+ E2E（Chromium）
```

## 已固化缺陷（用例可复现）

| 编号 | 现象 | 层次 | 严重级 |
|---|---|---|---|
| D01 | 启动提示访问 `:5001`，实际监听 `:8000` | 配置一致性 | P3 |
| D05 | `/api/image/<uuid>` 资源不存在仍返回 200 + 全 null | 接口契约 | P2 |
| D06 | `page=0` / `per_page=-1` 走负索引切片，静默返回空页 / 少一条 | 边界处理 | P2 |
| D07 | `per_page` 无上限，可一次拉全量数据 | 资源耗尽 | P2 |
| D11 | `open()` 未指定 `encoding`，中文 Windows 下两个接口直接 500 | 跨平台兼容 | **P1** |
| D13 | `/api/filter` 的 `cit_label` 回退用 detection 标签匹配，标签空间混用误命中 | 业务逻辑 | P2 |
| D17 | `images.html` 调用从未定义的 `loadFilterOptions()`，每次加载抛 ReferenceError | 前端 | P2 |
| D18 | 前端 `fetch().then(r => r.json())` 未校验响应类型，单接口 500 导致整批失败 | 前端健壮性 | P2 |

另有 10 条静态分析发现的隐患（URL 拼接注入、全站关闭 TLS 校验、裸 `except`、无鉴权下载等），完整 20 条见 [缺陷清单](docs/02-缺陷清单.md)，含 4 份标准缺陷报告（复现步骤 / 期望 vs 实际 / 根因 / 影响 / 修复建议 / 回归用例）。

## 修复记录（2026-11-08）

已修复 3 个影响最直接的缺陷，**验证标准统一是"对应缺陷用例由 XFAIL 转为 XPASS"**：

| 缺陷 | 修复内容 | 验证结果 |
|---|---|---|
| **D11** P1 | `open()` 增加 `encoding='utf-8'`（3 处），消除中文 Windows 下 GBK 解码失败 | 2 条用例 XPASS，`/api/images_count` 恢复 200 |
| **D17** P2 | 删除 `images.html` 中对未定义函数 `loadFilterOptions()` 的调用 | 页面不再抛 ReferenceError |
| **D18** P2 | 抽出 `fetchJson()`，先校验 `res.ok` 再解析，错误信息可读 | 页面加载无未捕获异常 |

回归结果：`24 passed, 8 xfailed, 3 xpassed`（接口）＋ `7 passed, 2 xpassed`（E2E）。

剩余 5 个已复现缺陷（D01 端口提示、D05 资源不存在返回 200、D06 分页负索引、D07 `per_page` 无上限、D13 标签空间混用）保留为**已知问题**，对应 xfail 用例继续作为回归基线；它们都需要产品决策或跨端改造，不适合在测试仓库里单方面修改。

> 修复通过 `tools/bootstrap_fixtures.py` 的 `apply_fixes()` 固化：重新生成 SUT 副本时会重新打补丁，`assert` 保证锚点不漂移。

## 设计上值得说的几点

1. **测试数据与生产数据分离**：真实数据 549MB（`pose_results_all.json` 366MB），直接用于测试会让 CI 无法运行。改用 3 条定长记录的 seed 数据集，启动从分钟级降到秒级；代价是 SUT 需要支持 `GUOHUA_DATA_DIR` 注入——这就是"为可测性改造被测系统"。
2. **xfail 表达契约，而不是迁就现状**：缺陷用例断言"应该 404"，而不是"当前返回 200 所以断言 200"。修复后自动 XPASS，缺陷与用例同生共死。
3. **就绪探测用轮询而非 sleep**：避免固定等待造成的 flaky 和慢测试。
4. **踩过一个典型坑并修掉**：SUT 的 stdout 最初用 `subprocess.PIPE`，500 响应的 traceback 把管道缓冲区写满后，被测进程阻塞在 `write` 上，表现为"所有请求无响应"的假死。改为重定向到 `test-output/sut.log` 后解决，并顺带获得了可追溯的服务端日志。
5. **接口测试 + E2E 互补**：D17/D18 两个缺陷接口层完全看不见——接口都是 200，但页面初始化抛异常、筛选计数永久为 0。反过来 E2E 也发现不了 D06/D07 这类参数边界问题。两层缺一不可。
6. **修缺陷要看调用方**：前端第 637 行依赖 `api/images?per_page=20000` 拉全量，说明 D07（无上限）已经被调用方依赖。如果只给接口加 500 上限，页面会静默少数据而不报错——所以 D07 必须连带前端分页一起改。
7. **CI 自包含**：`sut/` 目录随仓库提交，CI 不需要原项目即可运行。

## 局限与后续

- `/api/scroll`、`/api/thumb`、`/api/images/<path>`、`/api/download` 依赖云端图片服务（已脱敏为示例域名），当前未接入 mock：用 `requests-mock` 打桩后可覆盖"第三方依赖超时/异常返回 → 服务端应如何降级"。
- 无性能用例：`/api/scroll` 的瓦片拼接是 N 次串行 HTTP，天然是 P95 长尾点，待接入 Locust 做容量与稳定性测试。
- E2E 只跑 Chromium，未覆盖多浏览器与移动端分辨率；也未覆盖上传/下载等需要真实文件的链路。

## 脱敏说明

被测系统来自课题组内部项目，公开前做了三项处理，业务逻辑与缺陷均保持原样：

1. 云端服务域名统一替换为不可解析的示例域名（`cloud.example.invalid`）
2. 全部 seed 数据为**合成数据**，不含真实藏品元数据、标注结果与数据集 ID
3. 仅保留测试所需的最小数据规模（原真实数据 549MB，仓库内约 550KB）
