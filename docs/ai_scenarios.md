# 模块 7 V0.1：AI 辅助场景建议

本文保留 V0.1 的设计说明；V0.3 增加可选 intended_value、输入一致性检查、重复输入标记及明确的人工审查状态，见 [质量检查说明](ai_quality.md)。
文中的“尚未验证真实服务”等描述属于 V0.1 时点；后续两次真实模型调用与质量评价见 [真实验收记录](../reports/ai_real_acceptance.md)。

本模块只生成待人工审查的建议，不执行接口测试。
V1.0 的 CLI、OpenAPI 解析器、测试用例生成器和执行链路保持原样。
不安装大模型 SDK，HTTP 调用复用已有 requests 依赖。

## 模块职责与调用边界

```text
parse_openapi() 的接口元数据（含 parameters.schema）
  → generate_scenarios(interface)
  → AIClient.generate(prompt)：唯一的大模型 HTTP 调用
  → parse_suggestions()：JSON、字段、参数引用和策略校验
  → 待审查建议（executable=false）
```

- `ai_client.py`：读取服务环境变量，调用非流式 Chat Completions 接口，检查响应外层结构和完成状态。
- `ai_scenario_generator.py`：构造提示词、校验模型 JSON、依据文档约束生成输入值、标记来源和待补充信息。
- `generate_scenarios(interface, client=...)` 可注入具备 `generate(prompt)` 方法的客户端，方便离线测试或以后替换服务适配器。
- 保持现有 `case_generator.py` 职责；建议结果没有 `executable_cases`，也没有执行所需的 URL 和 `expected_status`。

适配器使用 `model`、`messages` 请求字段以及 `choices[0].message.content` 响应格式，
参考 [官方 Chat Completions API 文档](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。
服务和模型必须兼容此格式；本阶段尚未验证任何真实模型服务。

## 三种信息来源

| 输出字段或标记 | 含义 |
| --- | --- |
| `openapi_declared` | 从现有解析结果复制的接口路径、方法、参数约束及 Body 存在标志；认证样例会省略，敏感文本会脱敏 |
| `ai_inferred` | AI 选择的场景分类、意图和输入策略；不是已验证的接口行为 |
| 输入的 `source=openapi_declared` | 输入值取自文档的 example、enum、default、minimum 或 maximum |
| 输入的 `source=ai_inferred` | 合成的越界数据或有意省略参数 |
| `user_required` | 用户需要提供的参数值、业务数据、认证信息和预期断言 |
| `expected_result` | `status_code=null`、`body=null`、`confirmed=false`，始终待用户确认 |

解析器的 summary 可能是默认文本，因此不把它标成 OpenAPI 明确声明。
参数约束被复制并保留，不把未声明的业务规则标成文档事实。
选择哪个文档值用于场景本身仍属于 AI 推断；输入值的来源单独记录。

## AI 输入策略

模型提交参数名称、位置和策略，不能提交任意 `value`，输入数据由程序生成。

| 策略 | 输入数据 |
| --- | --- |
| `declared_value` | 优先使用参数 example、schema example、enum 第一项或 default |
| `minimum` / `maximum` | 使用声明的数值下界／上界 |
| `below_minimum` / `above_maximum` | 使用下界减一／上界加一，标记为推断的合成输入 |
| `omit` | 有意省略参数；`value=null`，不表示发送 JSON null |
| `user_supplied` | `value=null`，用户仍需提供真实数据 |

Header、Cookie 和识别出的凭证参数仅允许 `omit` 或 `user_supplied`，不会生成凭证值。
业务 ID、用户名等没有文档示例的参数需要用户提供；不根据类型凭空填入正常业务数据。
越界数据只是约束测试候选值，不声称该输入对应一个已存在的业务对象。

## 模型 JSON 合同与校验

模型须返回一个 JSON 对象，只有 `scenarios` 数组，包含 3–30 条建议，覆盖
`normal`、`boundary`、`negative` 三类。原始合同示例见 `examples/ai_mock_response.json`。
每条建议包含：`name`、`category`、`intent`、`inputs`、`expected_result`。

校验会拒绝无效 JSON、Markdown 包裹、重复 JSON 字段、额外字段、缺失字段、重复名称、
未知参数、重复输入、未知策略、缺少约束的取值策略，以及任何确定的预期状态码或响应 Body。
预期说明也不能夹带数字状态码。模型不能自行填写来源标记或确认标记，来源由程序设置。
任意一条无效都会使整份输出抛出 `AIOutputError`，不部分接纳、不自动修复、不自动执行。

## 服务配置和密钥

本阶段未读取或调用真实服务。未来单独验收时，在本机环境设置：

| 环境变量 | 含义 |
| --- | --- |
| `APIPILOT_AI_URL` | 完整 HTTPS Chat Completions endpoint，例如服务商提供的 `/v1/chat/completions` 地址 |
| `APIPILOT_AI_MODEL` | 该服务实际支持的模型名称，不提供猜测的默认模型 |
| `APIPILOT_AI_API_KEY` | 从环境读取的 Key，不写入源码、JSON、`.env` 文件或 Git |

没有内置服务地址或真实模型名。配置缺失时明确报错。
默认 30 秒连接／读取等待超时，可使用 `AIClient(timeout=...)` 调整；保留 HTTPS 证书校验，
不跟随重定向、不自动重试、不打印请求或原始服务响应。
网络失败只保留异常类型，HTTP 失败保留状态码，避免原始异常内容泄露 Key。
输出回显环境 Key 时直接拒绝，文档中的常见凭证样例也会省略或脱敏。

配置好服务后可使用以下独立调用方式；此代码会发起真实模型调用，本阶段未执行：

```python
from src.apipilot.openapi_parser import parse_openapi
from src.apipilot.ai_scenario_generator import generate_scenarios
from src.apipilot.reporting import write_report

interface = parse_openapi("examples/ai_scenarios_openapi.json")[0]
suggestions = generate_scenarios(interface)
write_report(suggestions, "reports/ai_suggestions.json")
```

## 离线测试与示例

新增测试只使用临时假 Key 和 Mock 响应，并阻止真实 HTTP 请求：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ai_client.py tests/test_ai_scenario_generator.py -q
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q
```

重新生成离线示例建议：

```powershell
.\.venv\Scripts\python.exe -c "import runpy; from pathlib import Path; helpers = runpy.run_path('tests/test_ai_scenario_generator.py'); helpers['generate_mock_example'](Path('examples/ai_suggestions_mock.json'))"
```

示例使用 `examples/ai_scenarios_openapi.json` 的 limit 参数：example=10、minimum=1、maximum=100。
`examples/ai_suggestions_mock.json` 是离线 Mock 流程的实际输出，不是真实大模型生成的结果。
正常候选值 10 和上界 100 来自文档；越界值 101 来自 maximum+1 的合成策略。
所有预期状态码和响应 Body 均待确认。

## 当前限制

- 未验证真实服务的可用性、模型效果或稳定性；Mock 仅验证集成代码逻辑。
- 只接受当前解析器提供的 GET/POST 元数据，逐接口调用，不接入现有自动执行流程。
- 第一版支持少量参数策略，不是完整 JSON Schema 验证器；不解析组合 Schema 或 `$ref`。
- 最小／最大策略处理数值 minimum/maximum；不自动推导 exclusiveMinimum、multipleOf、字符串长度、pattern 等组合规则。
- 现有解析器只暴露 Body 存在标志；Body Schema、具体业务 Body、响应 Schema 和 OpenAPI security 未提取，明确留给用户补充。
- 文档声明值仍可能过期或不符合真实业务条件；模型文字的语义正确性仍需人工审查。
- 对常见凭证和已配置 Key 做防护，不承诺识别文档或模型文字中任意未知的敏感格式。
- 暂无流式响应、工具调用、多轮修复、重试或模型质量评估。
