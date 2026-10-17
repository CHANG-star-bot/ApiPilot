# 模块 7 V0.3：AI 建议质量检查

本阶段不调用真实模型、不修改 V1.0 执行器、不新增依赖。
检查仍位于独立的 `ai_scenario_generator.py` 中。

## 1. submit / preview 的根本原因

V0.2 记录中的选择是：

```json
{"name": "mode", "in": "query", "strategy": "declared_value"}
```

OpenAPI 的 mode 枚举为 `["preview", "submit"]`。`_input_data()` 按既有优先顺序选值：

```text
参数 example → schema.example → enum[0] → default
```

该参数没有 example，因此程序正确生成 `preview`。问题包含三个层面：

1. 模型给建议起了 submit 名称，却选用了只能得到 preview 的策略。
2. 策略映射符合当时合同，没有把 submit 错误地改成 preview；第一版策略不能选择任意 enum 项。
3. 当时没有结构化的输入意图声明和一致性检查，重复输入也只在独立验收脚本中统计。

V0.2 没有保存原始响应文本。这里依据保存的建议名称、策略、生成值和映射代码追踪问题，
不声称重新读取了原始服务响应。历史真实报告保持原样。

## 2. 完整生成流程

```text
parse_openapi() 提供接口元数据
  → build_prompt() 说明合同和选值顺序
  → client.generate(prompt) 返回文本（本阶段测试用 Mock）
  → parse_suggestions() 严格解析 JSON、检查整批字段和类别
  → _validate_scenario() 校验参数引用与策略
  → _input_data() 根据文档生成数据
  → _check_input_consistency() 检查结构化意图与生成值
  → _mark_duplicate_inputs() 标记同一接口的重复输入
  → 脱敏输出：executable=false，review.status=PENDING
```

`validate_scenario()` 复用同一条生成与一致性检查路径，供单条诊断和简单规则基线使用。
单条诊断不检查整批数量、类别覆盖、名称唯一和重复输入，也不能授予执行权限。

## 3. 新增可选 intended_value

模型输入可以增加 `intended_value`，它是 AI 对目标数据的声明，不是请求数据的覆盖值。
程序始终先按已有策略生成 `value`，再核对两者。

正确的声明：

```json
{"name": "mode", "in": "query", "strategy": "declared_value", "intended_value": "preview"}
```

不一致的声明：

```json
{"name": "mode", "in": "query", "strategy": "declared_value", "intended_value": "submit"}
```

第二种会抛出 `AIOutputError: intended_value does not match strategy-generated input`，
整批拒绝，不把输入改成 submit，也不重新调用模型。
`intended_value_source=ai_inferred` 与真正生成值的来源分别记录。

支持范围仍是原有七种策略：

- declared_value、minimum、maximum、below_minimum、above_maximum 可以核对 intended_value。
- omit、user_supplied 不允许附带 intended_value，避免把省略或未知输入误当成确定数据。
- 新提示词要求具体取值策略填写声明；旧输入没有这个字段仍兼容，但 input_consistency 为 UNCONFIRMED。
- 正常类场景使用越界策略，或显式省略文档声明的必填参数，会直接报错。
- 比较不做类型转换：整数 1、浮点 1.0、字符串 "1"、布尔 true 不自动视为相同。

不扫描名称中的 submit、preview、成功、失败等关键词来决定数据。
即使名称写 submit、结构化声明和生成值都写 preview，程序也只能确认结构化数据相符；
自然语言与业务意图仍需要人工判断。

## 4. review 的含义

每条输出增加：

```json
{
  "review": {
    "status": "PENDING",
    "business_confirmed": false,
    "input_consistency": "CHECKED",
    "duplicate_of": null,
    "duplicate_kind": null,
    "reasons": ["Confirm free-text name/intent against inputs and actual business behavior"]
  }
}
```

CHECKED 只表示本阶段能核对的输入声明一致，不代表自然语言或业务规则正确。
缺少声明、需要用户提供数据或没有结构化输入时，为 UNCONFIRMED。
所有输出的业务确认仍为 false，预期状态码与响应 Body 仍为 null，不进入自动执行链路。

## 5. 重复输入的口径和处理方式

`input_signature()` 使用生成后的参数位置、名称和数据建立稳定签名：

- 忽略建议名称、分类、策略名称和参数排列顺序。
- 不同策略得到同样的数据也能识别，例如 example=10 和 minimum=10。
- 显式 omit 与未提供该参数表示同样的省略。
- JSON 对象键顺序不影响比较；数组顺序和 JSON 数据类型保留。
- user_supplied 是未知占位符，不能与具体 JSON null 混同。
- 每次只比较一个接口，不跨接口保留状态。

发现重复后，后出现的建议标记 `duplicate_of`，指向首次出现的建议：

| duplicate_kind | 含义与处理 |
| --- | --- |
| concrete | 已生成的具体参数输入相同；人工合并建议或修改输入后重新校验 |
| template | 含 user_supplied、未知 Body 或未解析引用；只证明已知模板相同，补齐数据后再判断是否真正重复 |

保留全部建议和意图，追加明确的 review.reasons，不自动删除、改写或合并。
这样可以保留不同测试意图供审查，并避免把尚未提供的不同业务数据误判成确定重复。
本阶段没有把待审查建议提升为业务有效或可执行用例。

独立验收脚本复用同一个签名函数，统计口径随之统一；重复计数包含可能的模板重复，
具体类型需查看每条建议的 review。历史 V0.2 数字仍按当时口径记录，不被覆盖。

## 6. 离线验证与限制

新增 `tests/test_ai_scenario_quality.py`，覆盖：

- 五种具体策略的正确声明、不一致声明及类型不匹配。
- submit/preview 回归、example 优先级、自由文本仍待人工确认。
- 正常类越界/必填省略冲突、可选省略、未知业务语义。
- 不同名称/分类/策略、参数顺序、显式省略、未知占位符和 Body 的重复处理。
- Mock 生成链路及错误信息不回显输入数据。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ai_scenario_quality.py tests/test_ai_scenario_generator.py tests/test_ai_acceptance.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

本次实际完整回归：修改前 `268 passed, 9 deselected`；修改后
`302 passed, 9 deselected in 1.30s`，退出码 0。
新增 34 个离线测试用例（包括参数化展开及验收统计一致性测试）。
9 个真实业务集成测试按默认设置未执行；本阶段真实模型调用为 0 次。

还使用 V0.2 报告中保存的名称、策略和预期说明重建了旧合同字段，离线重新解析：

| 历史建议 | 数量 | 业务待确认 | 输入一致性未确认 | 模板重复 |
| --- | --- | --- | --- | --- |
| GET /items | 8 | 8 | 7 | 1 |
| POST /reviews/{item_id} | 8 | 8 | 8 | 1 |

GET 的合法数值 user_supplied 与非整数 user_supplied 具有相同的未知占位模板；
不能因此断言它们未来会使用相同具体数据。
POST 的 submit 建议仍生成 preview，并标记为与 preview 建议模板重复、待人工审查。
没有凭名称猜测或修复数据。
重建不是原始响应回放，也不是新的模型调用；没有覆盖历史真实报告。

仍需人工审查自然语言与数据的关系、业务规则、认证和 ID、Body 内容、预期断言。
当前不是完整 JSON Schema 校验器，也不能自动选择 enum 第二项或理解任意业务语义。
本阶段没有真实模型调用，离线测试不能证明新的提示词对真实模型的生成质量有何改善。
