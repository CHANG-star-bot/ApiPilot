# 模块 7 V0.2 真实模型验收记录

验收日期：2026-10-13（Asia/Shanghai）。

## 结论

真实模型调用和结构校验通过；建议质量仍需人工审查。
本次只调用模型服务，没有执行建议中的 GET /items 或 POST /reviews/{item_id}。
它们是本地合成 OpenAPI 文档，不对应已部署的业务服务。
没有用 Mock、monkeypatch 或测试辅助函数替代本次模型请求。

请求路由：`openrouter/free`。真实模型请求共 2 次，成功返回文本 2 次，无重试。
完整程序生成报告：[ai_real_acceptance.json](ai_real_acceptance.json)。
没有核查账户账单，不能把本次结果描述为已经核对过扣费记录。

## 实际执行命令

从 Windows 用户环境载入配置，不在命令中填写或输出 Key：

```powershell
foreach ($settingName in @('APIPILOT_AI_URL', 'APIPILOT_AI_MODEL', 'APIPILOT_AI_API_KEY')) {
    [Environment]::SetEnvironmentVariable($settingName, [Environment]::GetEnvironmentVariable($settingName, 'User'), 'Process')
}
if ($env:APIPILOT_AI_URL.Trim() -ne 'https://openrouter.ai/api/v1/chat/completions' -or $env:APIPILOT_AI_MODEL.Trim() -ne 'openrouter/free') {
    Write-Output 'Stopped: configuration does not match the selected free route'
    exit 2
}
.\.venv\Scripts\python.exe -m examples.run_ai_acceptance --report reports/ai_real_acceptance.json --timeout 30
```

实际输出：

```text
STATUS=VALIDATED CALLS=2 RESPONSES=2
GET /items: VALIDATED
POST /reviews/{item_id}: VALIDATED
EXIT_CODE=0
```

`VALIDATED` 仅表示整批结构校验通过；不是人工质量验收通过，也不是业务接口测试 PASS。

## 数量与实际模型

| 指标 | GET /items | POST /reviews/{item_id} |
| --- | --- | --- |
| 服务返回的实际模型 | apodex/apodex-1.1-mini:free | nvidia/nemotron-3-super-120b-a12b:free |
| 原始 JSON 类型 | object | object |
| 原始建议数 | 8 | 8 |
| 正常 / 边界 / 异常 | 2 / 2 / 4 | 3 / 2 / 3 |
| 单条结构无效数 | 0 | 0 |
| 重复名称数 | 0 | 0 |
| 重复输入签名数 | 0 | 1 |
| 整批接纳数 / 拒绝数 | 8 / 0 | 8 / 0 |
| 简单规则候选数 | 7 | 14 |
| 规则未覆盖的独特签名数 | 1 | 7 |

重复签名口径为“类别 + 排序后的参数名称、位置和策略”。
两组总计 16 条通过结构校验；按该口径有 15 个组内独特输入签名。
重复和语义不一致不会使现有结构检查自动失败。
本次人工确认 1 条名称/意图与实际输入不一致，详见下文。

## 人工质量审查与规则比较

### GET：主要复述已有规则，增益较小

模型覆盖 example=10、minimum=1、maximum=100、越界 0/101 和省略必填 limit。
这些策略简单规则已经可以生成。

新增签名来自异常类的 `user_supplied`，意图为检验非整数 limit。
这提供了类型错误测试的提示，但实际值仍为 null，用户需要提供具体非整数输入；
不能宣称模型已经生成了可执行的类型错误数据。

所有预期状态码和响应 Body 仍为 null，待人工确认。
“接受最小值”“拒绝越界”等文本属于测试意图，未验证真实接口行为。

### POST：组合上下文有帮助，但出现语义错误

模型将 item_id、rating、mode、Authorization 组合到同一场景，覆盖评分上下界、越界、
省略认证和省略可选 mode。相比逐参数规则候选，这种组织方式更便于人工审查。
7 个新增签名主要来自多参数组合，不能据此认定新增了 7 种业务规则或证明模型质量优于规则。

具体问题：

- `Normal request with submit mode` 的名称和意图要求 submit 模式。
- 模型选择的策略仍是 `declared_value`；现有生成器按合同取 enum 第一项 `preview`。
- 因此实际输入与 `Normal request with preview mode` 相同，构成 1 个重复输入签名，
  同时存在 1 条名称/意图与输入不一致的建议。两项计数描述的是同一条问题，不应相加。
- 现有策略不能选择 enum 的第二项；本次保留真实输出，没有改成 submit，也没有再次调用模型。

### 仍需用户补充

- 所有建议的预期状态码和响应断言。
- GET `user_supplied` 场景的具体合法数值和非整数测试数据。
- POST 的真实 item_id、有效认证信息和经批准的业务 Body。
- 当前解析器只提供 requestBody 存在标志，未把其 Schema 交给模型，需要人工补充 Body 约束。

本次未在结构化输入中发现编造的认证值、业务 ID、Body 或确定的预期状态码。
正常业务 ID 和认证值均保留为 null / user_required；所有结果都是 executable=false。
“没有发现”仅针对本次两组输出，不代表对任意模型输出的保证。

## 离线回归

真实调用结束后执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

实际结果：`268 passed, 9 deselected in 2.16s`，退出码 0。
9 项真实业务 API 集成测试按默认设置未执行。
离线 Mock 测试与上面的 2 次真实模型调用分别记录，不互相替代。

## 当前限制

- 只有两组样本，每组调用一次，并且免费路由返回了不同模型，不能据此比较模型优劣或稳定性。
- 单条结构检查不验证自然语言意图与生成数据的一致性，本次 submit/preview 问题体现了这一限制。
- 策略仅覆盖少量已支持的参数约束；不覆盖完整 JSON Schema、任意 enum 取值、Body 或业务规则。
- 规则比较采用较简单的逐参数基线；新增签名数量不是质量分数。
- 没有执行模型建议对应的业务请求，没有验证这些预期意图是否符合实际服务。
- 不接入 V1.0 自动执行链路；本次没有为了让输出通过而修改提示词、输入策略或校验规则。

本次只更新程序生成的 JSON 报告并新增本验收记录，没有修改 Python 源码或安装依赖。
