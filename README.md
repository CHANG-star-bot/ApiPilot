# ApiPilot

ApiPilot 是一个用于测试开发实习准备的个人 Python 接口自动化测试项目。
开发过程使用 AI 辅助，重点学习请求封装、数据与代码分离、断言、异常处理和版本控制。
当前阶段为 V1.0：从本地 OpenAPI JSON 和显式测试配置生成用例，批量执行并保存 JSON 报告。

模块 7 V0.1 新增独立的 AI 场景建议模块，复用现有解析结果，不接入自动执行链路。
建议区分文档声明、AI 推断和用户待补充信息；所有预期结果均需确认。
使用方式、环境变量及离线 Mock 示例见 [AI 场景建议说明](docs/ai_scenarios.md)。
模块 7 V0.2 的独立真实调用入口、免费服务配置及质量验收口径见 [模型验收说明](docs/ai_acceptance.md)。
模块 7 V0.3 的输入一致性、重复建议处理及人工审查边界见 [AI 建议质量检查](docs/ai_quality.md)。

## 从零安装与验证

本次验证环境为 Python 3.12.4。请先安装 Python 3.12，并在项目根目录执行：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.apipilot.cli --help
```

直接使用虚拟环境中的 Python 即可，无需先激活环境。
依赖固定在 requirements.txt 中；运行离线测试不需要 API Key 或外部 API。
2026-10-17 本地离线回归结果为 302 passed、9 deselected。交付复现记录见 [首次提交验收](docs/delivery_acceptance.md)。

## 先理解这条主线

```text
接口说明 + 人工填写的输入和预期
  → 生成用例 → 发送 GET/POST → 检查响应 → 汇总并保存报告
```

| 位置 | 用途 |
| --- | --- |
| src/apipilot/ | 请求、断言、用例生成、CLI 和独立 AI 建议模块 |
| tests/ | 离线单元测试与单独标记的真实 integration 测试 |
| cases/ | 早期参数化练习使用的 JSON 用例 |
| examples/ | OpenAPI、测试配置和明确标记的 Mock 示例 |
| reports/ | 带有验收背景的历史真实结果 |
| docs/ | 设计说明、验收记录和学习导航 |

学习从 [请求与断言入门](docs/learning_guide.md) 开始，再逐步阅读批量执行、OpenAPI 和 AI。
AI 输出始终是待人工审查建议，不参与主执行流程。

## 命令行运行

在项目根目录使用项目的 `.venv`，查看入口参数：

```powershell
.\.venv\Scripts\python.exe -m src.apipilot.cli --help
```

仓库提供 JSONPlaceholder 真实 GET 验收配置。以下命令会向公开 API 发出两条真实 HTTPS 请求：

```powershell
.\.venv\Scripts\python.exe -m src.apipilot.cli --openapi examples/jsonplaceholder_openapi.json --config examples/jsonplaceholder_config.json --report reports/real_result.json --timeout 10
```

`--openapi`、`--config` 和 `--report` 为必填参数；路径相对于当前工作目录。
报告父目录会自动创建；已有报告会被替换，报告路径不能与输入文件相同。
正式运行入口为 CLI。`src/apipilot/main.py` 是早期保留的学习脚本，
其中查询 users/1 却断言 id=2，会故意断言失败，不作为项目启动入口。

真实验收配置固定检查 HTTP 200 及 `id`、`name`、`username`、`email` 字段，
字段来源为 [users/1](https://jsonplaceholder.typicode.com/users/1) 和
[users/2](https://jsonplaceholder.typicode.com/users/2) 的公开响应，执行前已核对。
实际命令、退出码及结果记录在 `reports/real_acceptance.md`；完整真实报告为 `reports/real_result.json`。

## 测试配置

配置使用现有生成器格式，按 `method` 和 `path` 匹配接口，例如：

```json
{
  "base_url": "https://example.test/api",
  "cases": [
    {
      "method": "GET",
      "path": "/users/{user_id}",
      "path_params": {"user_id": 1},
      "params": {"language": "zh"},
      "headers": {"Accept": "application/json"},
      "expected_status": 200,
      "expected_body": {"id": 1}
    },
    {
      "method": "POST",
      "path": "/users",
      "body": {"name": "Explicit test data"},
      "expected_status": 201,
      "expected_body": {"name": "Explicit test data"}
    }
  ]
}
```

以上状态码和数据只是配置格式示例，必须由测试者根据实际接口确定。
`expected_body` 可省略，此时只断言状态码；对象采用子集匹配，数组采用前缀匹配。
缺少预期状态码、必要路径参数、必填参数或声明的 Body 数据时，接口进入待补充清单，不执行。
格式错误的配置会直接报错；信息缺失的配置会保留待补充原因。

## 汇总、报告和退出码

执行链路：`parse_openapi → generate_cases → run_suite → run_case → send_request → assert_response`。
CLI 负责接收参数、打印汇总和调用报告保存，不重复实现生成和断言逻辑。

终端示例：`TOTAL=4 EXECUTED=4 PASS=2 FAIL=1 ERROR=1 PENDING=1`。
终端 `TOTAL`、`EXECUTED` 和 JSON 的 `summary.total` 统一表示已执行用例数，
等于 PASS + FAIL + ERROR。待补充接口由 PENDING 单独计数，不计入 TOTAL。
JSON 沿用 suite_runner 的结构：`summary.total` 为已执行数，`summary.pending` 为待补充数；
`results` 保存每条已执行用例的名称、状态和错误原因，`pending_cases` 保存待补充原因。

| 退出码 | 含义 |
| --- | --- |
| 0 | 至少执行一条用例，已执行用例全部 PASS；仍可能有 PENDING |
| 1 | 已执行用例中存在 FAIL 或 ERROR，报告正常保存 |
| 2 | 参数、输入文件、配置或报告写入错误，或没有可执行用例 |

没有可执行用例时仍保存空结果和待补充原因，并返回 2。
输入校验失败时不发送请求。单条用例 FAIL/ERROR 不阻止后续用例。
如果执行后报告写入失败，终端保留汇总，返回 2；原报告通过临时文件替换方式保护。

报告不保存完整请求头、请求体或响应体。保存前会遮盖配置中的敏感字段、请求头值、
URL 凭证及常见认证信息；响应值不匹配时省略原始期望值和实际值。
脱敏只影响报告及 CLI 错误提示，不改变实际请求和断言。
这是对常见格式的防护，无法保证识别第三方异常文本中任意未知的密钥格式；分享报告前仍应检查。
输入配置本身不经过脱敏，不要提交包含真实凭证的配置。

## 超时

`--timeout` 接受正有限秒数，默认 10 秒，应用于每条 GET/POST 请求。
也可以直接调用 `send_request(..., timeout=2.5)`、`run_case(..., timeout=2.5)` 或
`run_suite(..., timeout=2.5)`。
该值是 requests 的连接及读取等待超时，不是整个批次的总耗时上限；没有自动重试。

## 离线测试与真实 API 测试

默认只运行离线测试，无需外部 API：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

离线 CLI 测试使用 Mock 响应覆盖 PASS、FAIL、ERROR 和 PENDING，并阻止真实 HTTP 请求。
重新生成提交的离线示例报告：

```powershell
.\.venv\Scripts\python.exe -c "import runpy; from pathlib import Path; helpers = runpy.run_path('tests/test_cli.py'); raise SystemExit(helpers['run_mock_example'](Path('examples/cli_offline_mock_report.json')))"
```

该命令确实经过 CLI 参数解析、用例生成、批量执行和报告保存；HTTP 层使用 Mock，
有意产生 FAIL/ERROR，因此退出码为 1。`examples/cli_offline_mock_report.json` 不是实际 API 的集成测试结果。

原有真实公开 API 测试保留，并标记为 `integration`，需显式执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration -q
```

这些测试依赖网络及外部服务，其中保留了学习用的错误预期断言，可能失败。
离线测试通过并不能证明真实 API 可用。

## 当前限制

- 只读取本地 OpenAPI 3.0/3.1 JSON，仅执行 GET/POST。
- 不展开 `$ref`，不根据 Schema 自动生成业务数据、认证信息或预期断言。
- 对声明 requestBody 的接口仍保守要求显式提供 Body；不支持 GET Body 和必填 Cookie 参数。
- 按顺序执行，不支持并发、重试、批次总超时或复杂认证流程。
- 报告只提供汇总、状态和简要原因，暂不记录耗时和完整请求响应。
