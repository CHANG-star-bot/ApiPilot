# 模块 7 V0.2：真实模型验收

独立入口复用现有 `AIClient`、OpenAPI 解析器和建议校验器，不调用 V1.0 执行器。
所有建议都是 `executable=false`，不会自动向示例 API 发送请求。

## 免费服务与环境配置

ApiPilot 当前使用 Bearer API Key，不能直接使用本聊天窗口或 ChatGPT 订阅。
[OpenAI 说明](https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform)
明确区分 ChatGPT 与 API 计费。

可以先用 [OpenRouter 免费路由](https://openrouter.ai/openrouter/free)，无需选择付费模型。
官方标明其输入和输出 token 价格为零；免费额度、服务可用性以服务商当前说明为准。
此路由会选择不同的免费模型，所以报告同时记录请求的路由名称和服务返回的实际模型名称。
服务未提供模型名称时保留 null，不猜测。

注册后在 [Keys 页面](https://openrouter.ai/settings/keys) 创建 Key，在 PowerShell 执行：

```powershell
[Environment]::SetEnvironmentVariable("APIPILOT_AI_URL", "https://openrouter.ai/api/v1/chat/completions", "User")
[Environment]::SetEnvironmentVariable("APIPILOT_AI_MODEL", "openrouter/free", "User")
$apiKey = Read-Host "粘贴 API Key（输入不显示）" -AsSecureString
[Environment]::SetEnvironmentVariable("APIPILOT_AI_API_KEY", [System.Net.NetworkCredential]::new("", $apiKey).Password, "User")
Remove-Variable apiKey
```

这些值保存在 Windows 用户环境中；环境变量不是加密凭证库。
不要把 Key 粘贴到聊天、源码、测试配置或 Git。
完整请求地址与 Bearer 调用方式见 [OpenRouter 官方快速开始](https://openrouter.ai/docs/quickstart)。

已经打开的进程不会自动获得新配置。在运行命令的 PowerShell 中载入用户环境：

```powershell
foreach ($name in @("APIPILOT_AI_URL", "APIPILOT_AI_MODEL", "APIPILOT_AI_API_KEY")) {
    [Environment]::SetEnvironmentVariable($name, [Environment]::GetEnvironmentVariable($name, "User"), "Process")
}
```

随后在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m examples.run_ai_acceptance --report reports/ai_real_acceptance.json --timeout 30
```

此命令在配置齐全时发起真实模型调用。单次运行最多两次调用，每组一次；不自动重试、
不修复输出，服务/网络错误后停止后续调用。不会自行更换服务或付费模型。
超时仍是 requests 的连接/读取等待超时，不是整个运行的总时限。

## 两组示例与比较方法

- `ai_scenarios_openapi.json`：OpenAPI 3.0 GET `/items`，limit 示例和数值上下界。
- `ai_review_openapi.json`：OpenAPI 3.1 POST `/reviews/{item_id}`，rating 数值上下界、
  mode 枚举、未知业务 ID、认证 Header 和 requestBody 存在标志。

这些是本地合成的接口文档，没有真实服务或凭证。模型合同要求正常、边界、异常三类建议。
第二组文档虽然声明了 Body Schema，现有解析器只暴露 Body 是否存在；脚本不越过解析器读取
完整 Body，不编造业务数据，报告明确记录此限制及待补充事项。

简单规则基线逐参数尝试现有七种策略，只保留现有校验器支持的候选。
规则来源标记为 `rule_generated`，绝不标成真实模型建议。规则也不执行。
V0.3 起，比较复用生成器的输入签名：根据参数位置、名称和生成数据比较，忽略名称、分类及策略。
未知输入保留占位符，只能说明模板相同；详细规则见 [质量检查说明](ai_quality.md)。

| 报告指标 | 定义 |
| --- | --- |
| calls | 实际发起模型请求的次数，包含失败请求 |
| responses | 适配器成功返回文本的次数，不含拒绝/截断/外层格式错误 |
| raw_json_type / raw_categories | 原始文本的 JSON 类型及正常/边界/异常/未知类别数量 |
| invalid_items | 单条校验失败的建议数，不包含仅在整批检查中发现的问题 |
| duplicate_names | 相同名称超出第一次出现的数量，属于整批错误 |
| duplicate_inputs | 通过单条检查的建议中输入签名重复的数量，包含未知数据的模板重复；类型见 review.duplicate_kind |
| accepted_suggestions | 通过原有整批校验的数量；任何整批错误都使此值为零 |
| rejected_suggestions | 原始条数减去整批接纳条数，不能等同于单条错误数 |
| novel_inputs_vs_rules | 接纳建议中规则基线未覆盖的独特签名数量 |

`validate_scenario()` 复用整批校验的单条检查和输入生成逻辑，仅用于诊断和规则比较；
不能绕过 `parse_suggestions()` 的数量、三类覆盖、名称唯一等整批要求。
重复输入不会自动删改，V0.3 起标记 duplicate_of 和 duplicate_kind，保留待人工合并或修改的原因。
所有建议的 review.status 为 PENDING；整批无效时不保存或接纳部分建议。
不保存未经校验的原始模型文本，只记录计数、受控错误和通过校验后的脱敏建议。

**新组合数量不是质量分数。** 人工验收仍需看意图是否合理、是否遗漏必填参数、
是否只是重复边界规则、是否提出了有价值的参数组合；没有真实结果就不评价模型增益。
字符串边界、enum 第二项、业务 Body 等仍超出现有输入策略，不能据此夸大覆盖率。

## 退出码与离线回归

- 0：两组真实响应都通过结构校验，不代表建议已通过人工质量审查。
- 2：未配置、配置无效、服务异常、无效输出或准备/报告错误。

没有配置时报告为 `NOT_CONFIGURED`、calls=0，未观测指标为 null。
服务/格式错误保留真实受控错误，不以 Mock 补齐；无法解析的文本不猜测建议条数。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ai_acceptance.py tests/test_ai_client.py tests/test_ai_scenario_generator.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

上述测试使用离线 Mock，并阻止网络请求，只验证代码逻辑。
真实服务可用性、生成质量及跨模型稳定性必须在配置完成后单独验收。
