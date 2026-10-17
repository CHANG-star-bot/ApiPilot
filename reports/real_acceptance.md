# ApiPilot V1.0 真实端到端验收记录

日期：2026-10-10（Asia/Shanghai）

## 验收输入

- OpenAPI：`examples/jsonplaceholder_openapi.json`，包含两个具体 GET 路径。
- 测试配置：`examples/jsonplaceholder_config.json`。
- 预期状态码均为 200，响应按对象子集检查 `id`、`name`、`username`、`email`。
- 预期字段在执行前依据公开响应固定：[users/1](https://jsonplaceholder.typicode.com/users/1)、[users/2](https://jsonplaceholder.typicode.com/users/2)。没有根据执行结果修改断言预期。

## 真实 CLI 执行

工作目录：`D:\ApiPilot`。使用该项目的 `.venv`。

```powershell
.\.venv\Scripts\python.exe -m src.apipilot.cli --openapi examples/jsonplaceholder_openapi.json --config examples/jsonplaceholder_config.json --report reports/real_result.json --timeout 10
```

实际退出码：**0**。

实际终端输出：

```text
TOTAL=2 EXECUTED=2 PASS=2 FAIL=0 ERROR=0 PENDING=0
Report: reports\real_result.json
```

CLI 只执行了一次，直接使用正常 HTTP Client，没有 monkeypatch、Mock 或测试辅助函数。
使用 10 秒连接/读取等待超时，保持 requests 默认 HTTPS 证书校验，没有手工重试。
两条真实 GET 用例均通过 HTTP 状态码和响应字段断言。

## 实际 JSON 报告

以下内容读取自本次 CLI 生成的 `reports/real_result.json`：

```json
{
  "summary": {
    "total": 2,
    "PASS": 2,
    "FAIL": 0,
    "ERROR": 0,
    "pending": 0
  },
  "results": [
    {
      "name": "JSONPlaceholder GET /users/1",
      "status": "PASS",
      "error": null
    },
    {
      "name": "JSONPlaceholder GET /users/2",
      "status": "PASS",
      "error": null
    }
  ],
  "pending_cases": []
}
```

## 统计口径修正

验收前发现终端 TOTAL 包含 PENDING，而 JSON 的 summary.total 只统计已执行用例。
最小修正为仅修改 CLI 的 TOTAL 显示表达式，沿用现有 Suite Runner 和 JSON 定义：

- TOTAL = EXECUTED = summary.total = PASS + FAIL + ERROR = 已执行用例数。
- PENDING = summary.pending = 待补充用例数，不计入 TOTAL。
- 全部已识别接口数需要将 TOTAL 与 PENDING 相加。
- 本次终端与 JSON 均为 total=2、PASS=2、FAIL=0、ERROR=0、pending=0。

保留现有 EXECUTED 字段。新增四个离线统计回归场景：混合执行与待补充、全可执行、全待补充、空文档。

## 最后的离线回归

真实 CLI 执行后运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q
```

实际退出码：**0**。实际结果：

```text
........................................................................ [ 45%]
........................................................................ [ 91%]
.............                                                            [100%]
157 passed, 9 deselected in 1.32s
```

这些 pytest 结果属于离线回归；旧的 9 项 integration 测试未运行。
本记录中的两条真实 API 结果来自上面的独立 CLI 命令，不能与离线 Mock 测试混为一谈。

## 验收范围

本次证明当前环境下两个公开 GET 接口的 OpenAPI → 用例生成 → HTTP 请求 → 断言 → JSON 报告链路可用。
本次未验收真实 POST、认证流程或其他服务器，后续运行仍可能受网络及公开服务状态影响。
没有新增功能、第三方依赖或修改原有公开 API 测试数据。
