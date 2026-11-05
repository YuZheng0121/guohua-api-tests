# 国画分析 WebUI 接口自动化测试

[![api-tests](https://github.com/YuZheng0121/guohua-api-tests/actions/workflows/api-test.yml/badge.svg)](https://github.com/YuZheng0121/guohua-api-tests/actions/workflows/api-test.yml)

对一个真实 Flask 项目的接口层做自动化测试与缺陷挖掘：**21 个路由、29 条用例、3 秒跑完、发现 6 类已复现缺陷**。

被测系统（SUT）是一个真实的课题组内部 WebUI（992 行，中国绘画关键点/检测结果可视化），脱敏副本见 [`sut/app.py`](sut/app.py)。测试过程中对 SUT 只做了 3 处**可测性改造**（数据目录 / CSV 目录 / 端口支持环境变量），业务逻辑一行没改——缺陷保持原样，因为它才是测试对象。

## 快速开始

```bash
pip install -r requirements.txt
python -m pytest -q -rx          # 需在有 sut/ 数据的仓库根目录运行
```

```
20 passed, 9 xfailed in 5.18s
```

`xfailed` 不是失败，而是**已知未修复缺陷**：用例断言的是"正确契约"，当前实现不满足，因此预期失败；缺陷修复后它们会自动变成 XPASS。

生成 HTML 报告：

```bash
python -m pytest --html=test-output/report.html --self-contained-html
```

## 目录结构

```
guohua-api-tests/
├─ sut/                  # 被测系统副本（业务代码未改动）+ seed 数据 + 模板
│  ├─ app.py             # 原始 app.py，仅 3 处可测性改造
│  ├─ data/              # 小型 seed 数据（替代 549MB 真实数据）
│  ├─ csv_data/          # 朝代信息 CSV
│  └─ templates/
├─ conftest.py           # SUT 生命周期、HTTP 会话、固定 ID fixture
├─ tests/
│  ├─ test_smoke.py      # 20 条冒烟/契约用例（必须全绿）
│  └─ test_defects.py    # 9 条缺陷用例（xfail，表达正确契约）
├─ tools/bootstrap_fixtures.py   # 从原项目重建 SUT 副本与 seed 数据
├─ docs/
│  ├─ 01-接口清单与用例设计.md
│  └─ 02-缺陷清单.md
└─ .github/workflows/api-test.yml
```

## 已固化缺陷（用例可复现）

| 编号 | 现象 | 严重级 |
|---|---|---|
| D01 | 启动提示访问 `:5001`，实际监听 `:8000` | P3 |
| D05 | `/api/image/<uuid>` 资源不存在仍返回 200 + 全 null | P2 |
| D06 | `page=0` / `per_page=-1` 走负索引切片，静默返回空页 / 少一条 | P2 |
| D07 | `per_page` 无上限，可一次拉全量数据 | P2 |
| D11 | `open()` 未指定 `encoding`，中文 Windows 下两个接口直接 500 | P1 |
| D13 | `/api/filter` 的 `cit_label` 回退用 detection 标签匹配，标签空间混用误命中 | P2 |

另有 9 条静态分析发现的隐患（URL 拼接注入、全局关闭 TLS 校验、裸 `except`、无鉴权下载等），见 [缺陷清单](docs/02-缺陷清单.md)。

## 设计上值得说的几点

1. **测试数据与生产数据分离**：真实数据 549MB（`pose_results_all.json` 366MB），直接用于测试会让 CI 无法运行。改用 3 条定长记录的 seed 数据集，启动从分钟级降到秒级；代价是 SUT 需要支持 `GUOHUA_DATA_DIR` 注入——这就是"为可测性改造被测系统"。
2. **xfail 表达契约，而不是迁就现状**：缺陷用例断言"应该 404"，而不是"当前返回 200 所以断言 200"。修复后自动 XPASS，缺陷与用例同生共死。
3. **就绪探测用轮询而非 sleep**：避免固定等待造成的 flaky 和慢测试。
4. **踩过一个典型坑并修掉**：SUT 的 stdout 最初用 `subprocess.PIPE`，500 响应的 traceback 把管道缓冲区写满后，被测进程阻塞在 `write` 上，表现为"所有请求无响应"的假死。改为重定向到 `test-output/sut.log` 后解决，并顺带获得了可追溯的服务端日志。
5. **CI 自包含**：`sut/` 目录随仓库提交，CI 不需要原项目即可运行。

## 局限与后续

- `/api/scroll`、`/api/thumb`、`/api/download` 依赖云端图片服务（仓库内已脱敏为示例域名），当前未接入 mock，属待补：用 `requests-mock` 打桩后可覆盖"第三方依赖超时/异常返回 → 服务端应如何降级"。

## 脱敏说明

被测系统来自课题组内部项目，公开前做了三项处理，业务逻辑与缺陷均保持原样：

1. 云端服务域名统一替换为不可解析的示例域名（`cloud.example.invalid`）
2. 全部 seed 数据为**合成数据**，不含真实藏品元数据、标注结果与数据集 ID
3. 仅保留测试所需的最小数据规模（原真实数据 549MB，仓库内 536KB）
- 性能用例（`/api/scroll` 瓦片拼接的 P95 延迟、`/api/stats` 在大数据集下的响应时间）待接入 Locust。
- 未覆盖前端 E2E；后续用 Playwright 对四个页面做冒烟与关键路径回归。
