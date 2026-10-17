# ApiPilot 学习导航：为测试开发实习做准备

目标是亲手运行、修改、解释和排错。先学主执行链路，再看 OpenAPI 和 AI。
理解一轮后再开始下一轮，不要求一次读完所有文件。

## 第一轮：一条请求为什么通过或失败

阅读顺序：

1. `src/apipilot/case_runner.py`：从用例取出数据，交给请求函数。
2. `src/apipilot/http_client.py`：使用 requests 发送 GET/POST，返回响应对象。
3. `src/apipilot/assertions.py`：比较实际状态码和响应字段与预期。
4. `tests/test_request_flow.py`：用模拟响应验证这条链路，不访问网络。

先运行已有离线测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_request_flow.py -q
```

### 先掌握这几个 Python 概念

下面的例子用于解释字典取值，不发送请求：

```python
case = {"method": "GET", "expected_status": 200}

print(case["method"])          # GET
print(case.get("headers"))     # None，因为没有这个键
print(case.get("timeout", 10)) # 10，因为没有这个键，所以用默认值
```

- **字典 dict**：用键保存数据，case 是一个用例字典。
- **方括号取值**：`case["method"]` 要求这个键存在；不存在会抛出 KeyError。
- **get()**：适合可选字段，可以指定取不到时的默认值。
- **None**：表示目前没有值，不等于字符串 `"None"`。
- **函数参数**：`send_request(method=..., url=...)` 按名称把数据传给函数。
- **return**：把函数的结果交回调用者；`response = run_case(case)` 用变量接住响应。
- **import**：从其他模块使用函数；模块职责分开，调用时再组合。
- **assert**：检查条件；不满足时抛出 AssertionError，而不是返回 False。

`run_case()` 只返回响应，不代表测试通过。调用断言后，才能根据预期判断是否符合要求。
变量名中不能夹空格，例如 `strategy` 与 `strateg y` 不同；后者会导致语法错误，测试无法收集。

### 这一轮你应能回答

- 为什么 method/url 使用方括号，而 params/headers 使用 get？
- GET 的查询参数与 POST 的 JSON Body 分别传到哪里？
- 为什么状态码正确，还需要检查响应字段？
- `pytest.raises(AssertionError)` 为什么能让“预期断言失败”的测试通过？

练习只修改测试中的临时输入或新增自己的离线用例，保留已有验收数据。
尝试制造一个错误预期，解释报错，再恢复正确预期。

## 第二轮：数据与代码分离、pytest 和 Mock

阅读 case_loader.py 与 test_request_flow.py，再看参数化测试。

- JSON 保存不同输入与预期，Python 复用同一套执行逻辑。
- `pytest.mark.parametrize` 让同一个测试函数运行多组数据。
- Mock 提供可控制的模拟响应，用于验证本地逻辑。
- 离线测试通过不代表外部服务目前可用。

## 第三轮：批量执行和结果分类

阅读 suite_runner.py 及其测试。

- PASS：请求完成，响应符合预期。
- FAIL：收到了响应，但断言不满足。
- ERROR：请求或解析发生异常。
- PENDING：信息不足，尚未执行。

重点解释 try/except：为什么一条用例失败后，其他用例还能继续执行。

## 第四轮：OpenAPI、用例生成、CLI 和报告

阅读 openapi_parser.py → case_generator.py → cli.py → reporting.py。

接口文档描述接口，测试配置提供具体数据和预期，两者合并后才可能形成可执行用例。
解释缺少路径参数、Body 或预期状态码时为什么保留为待补充。
能够演示 CLI、退出码和 JSON 报告，并说明报告脱敏的作用。

## 第五轮：AI 建议与质量边界

最后阅读 ai_scenario_generator.py 与 ai_quality.md。

AI 提出测试意图，程序根据已声明的约束生成输入；结构校验不等于业务正确。
解释 submit/preview 的不一致、intended_value 检查及重复模板为什么需要人工确认。
这些建议始终不可自动执行。

## Git：每次练习都留下真实记录

```powershell
git status
git diff
git add 你实际修改的文件路径
git diff --cached
git commit -m "说明这次真实改动"
git push
```

commit 保存当前改动形成一个版本；push 把本地版本同步到远程仓库。
提交后可以继续修改，下一次 commit 保存下一版。
面试时只描述自己确实理解、练习和验证过的部分；学习项目可以如实说明 AI 辅助过程。
