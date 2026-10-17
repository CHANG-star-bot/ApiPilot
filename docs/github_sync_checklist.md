# ApiPilot 最小 GitHub 同步清单

> 历史快照：以下内容记录早期检查时的状态，包括当时的虚拟环境失效、尚无提交和 AI 未验收等情况。
> 后续已修复环境、完成两次真实模型调用和 302 项离线回归。
> 当前安装与运行方式以 README 为准；首次提交的实际结果见 [交付验收](delivery_acceptance.md)。

核对日期：2026-10-13（Asia/Shanghai）。本清单只记录本次能核对的本地事实，不代替 GitHub 发布或个人能力考核。

## 1. 当前证据与边界

| 内容 | 当前能确认的事实 | 不能据此推出的结论 |
| --- | --- | --- |
| 本地代码 | 有 HTTP GET/POST、JSON 用例加载、pytest 参数化、状态码及响应字段断言、批量汇总与 CLI 源码 | 用户已独立掌握这些技术，或项目已公开 |
| Git 状态 | 当前 master 尚无提交；未配置远程地址；5 个文件处于 AM（暂存后又修改），其他多数文件未跟踪 | 已提交、已推送，或远端内容与本地一致 |
| 真实 API 历史记录 | `reports/real_acceptance.md` 记载 2026-10-10 两条 JSONPlaceholder GET 通过；`real_result.json` 对应 PASS=2 | 当前网络仍可用、真实 POST 已验收、所有 integration 测试通过 |
| 离线历史记录 | 同一验收文档记录当时 157 passed、9 deselected | 这是现有全部代码的最新结果；9 条被排除的测试也通过 |
| 本次运行复核 | 尝试运行 pytest、CLI help 和依赖检查，均被失效的 `.venv` 阻断：其指向的 Python 3.13.1 解释器不存在；本次未定位到其他可用 Python | 本次测试已通过，或失败原因是业务代码缺陷 |
| AI 扩展 | 有模块和离线 Mock 示例；说明明确表示未验证真实模型服务 | 已接入真实大模型、已验证生成质量或自动执行 AI 用例 |
| 浏览器原型 | `sites/apipilot-demo` 有独立代码、嵌套 `.git` 和历史验证说明；说明定位为私有 JavaScript 演示 | Python 后端已上线，或公众可以访问 |

GitHub 无可见仓库、Drive 未检索到文件，沿用用户提供的截至 2026-10-12 的状态；本次未重新查询这些账号。Drive 不是 GitHub 同步的必要条件。

## 2. 首次上传的最小范围

建议首版上传完整的小型 Python 项目，先不纳入浏览器原型。

| 上传范围 | 文件与用途 |
| --- | --- |
| 根目录 | `README.md`、`requirements.txt`、`pytest.ini`、完善后的 `.gitignore` |
| `src/apipilot/` | 所有现有 `.py`：`__init__`、`http_client`、`case_loader`、`case_runner`、`assertions`、`openapi_parser`、`case_generator`、`suite_runner`、`reporting`、`cli`、`main`、`ai_client`、`ai_scenario_generator` |
| `tests/` | 所有现有 `test_*.py`，保留离线与 integration 的分类；`.gitkeep` 无需上传 |
| `cases/` | `user_cases.json`，作为参数化输入示例 |
| `examples/` | 现有 OpenAPI、配置与 Mock JSON 文件；明确 Mock 输出的来源，上传前逐一检查是否含私人数据或真实凭证 |
| `docs/` | `ai_scenarios.md`、本清单，以及后续补充的复现记录 |
| `reports/` | 只选择历史 `real_acceptance.md`、`real_result.json` 和后续经检查的验收证据；历史文件保留原日期，不伪装成新结果 |

`main.py` 是旧学习脚本，其中 GET /users/1 却断言 id=2；应在 README 标为故意失败的学习示例，并使用 CLI 作为正式入口。`tests/test_user_api.py::test_get_wrong_user_id` 同样有意使用错误预期。

不上传：`.venv/`、`.idea/`、`__pycache__/`、`.pytest_cache/`、真实 `.env`、密钥/凭证、私人运行配置、未经检查的日志与临时报告、任何 `.git/` 目录。

当前 `.gitignore` 只有环境和缓存规则。建议补充 `.idea/`、`.env`、`.env.*`、`!.env.example`（仅在确有无密钥模板时使用）和项目实际使用的本地凭证文件规则。忽略规则不能移除已暂存的文件，仍须检查暂存清单。

`sites/` 本次不纳入：它包含独立 Git 仓库和部署材料，直接对根目录全部暂存可能形成嵌套仓库条目。以后单独同步演示源码与静态资源，并注明其 JavaScript 适配、私有访问范围和 Python 集成边界。

## 3. README 最少补充什么

现有 README 已有执行链路、CLI、离线/集成测试区分、退出码和限制，不必重写。补充以下内容即可：

1. **状态和贡献方式**：明确“学习项目；本地阶段成果”。推送后再填真实仓库链接与可见性；如使用 AI 辅助，说明辅助生成、本人实际修改和人工确认的范围，未确认的贡献不归为独立完成。
2. **从零安装**：写明实际验证的 Python、requests、pytest 版本；给出创建虚拟环境和安装依赖的步骤，不要求读者复用本机 `.venv`。目前历史环境配置为 Python 3.13.1，依赖文件固定 requests 2.34.2、pytest 9.1.1，尚未完成新环境复现。
3. **目录导航与最短演示**：数据文件 → 请求 → 断言 → 汇总；提供离线运行命令、预期输出和一条可解释的失败示例。
4. **验证矩阵**：按日期/提交版本分别列离线 Mock、真实 GET、真实 POST、真实模型服务；每项填写命令、退出码、计数和未验证内容。被 deselected 的用例不计为通过。
5. **失败示例说明**：旧 `main.py` 与错误 id 用例不是成功验收项。可以移入明确的学习示例，或使用原因明确的 `xfail(strict=True)`；不要改断言迎合实际结果，也不要隐藏真实回归失败。
6. **限制和报告口径**：保留对象子集/数组前缀断言、GET/POST 范围、不展开 `$ref`、无复杂认证/并发/重试等边界。说明 PASS/FAIL/ERROR/PENDING 和 TOTAL 计数规则。

## 4. 提交前的可运行验证门槛

以下为待执行门槛；本次没有把命令写出当成执行成功，也未重建环境或改动业务代码。

### A. 从干净环境复现（必须）

安装可用 Python 后，在干净目录或新环境操作，保留旧环境用于排查；以下用 `.venv-sync` 避免覆盖原 `.venv`。不要上传该环境目录。

```powershell
python -m venv .venv-sync
.\.venv-sync\Scripts\python.exe --version
.\.venv-sync\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-sync\Scripts\python.exe -m pip check
.\.venv-sync\Scripts\python.exe -m src.apipilot.cli --help
.\.venv-sync\Scripts\python.exe -m pytest -m "not integration" -q
```

记录实际 Python/依赖版本、退出码、通过及排除计数。安装失败或测试失败须如实保留，不沿用 157 作为现有版本结果。使用此临时环境时在忽略规则中加 `.venv-sync/`。

### B. 离线端到端及失败识别（必须）

按现有 README 的 `run_mock_example` 命令生成报告，输出路径改为临时目录，保留原示例。检查四类状态、汇总与逐条结果一致；这个演示故意制造 FAIL/ERROR，**预期退出码是 1**。确认错误状态码、字段不匹配、超时及缺少必要数据能被区分，失败后后续用例仍执行。Mock 输出不能作为真实 API 验收。

### C. 真实请求（要声称当前真实可运行时必须）

```powershell
.\.venv-sync\Scripts\python.exe -m src.apipilot.cli --openapi examples/jsonplaceholder_openapi.json --config examples/jsonplaceholder_config.json --report reports/real_result_recheck.json --timeout 10
```

预期退出码 0，TOTAL=2、PASS=2、FAIL=0、ERROR=0、PENDING=0。记录真实日期和终端输出；输入预期值必须先确定。若网络不可达，标记本次未完成，仍可提交明确标注的历史记录，不能写当前真实验收通过。

如简历要写“真实 POST 测试通过”，另外运行 `tests/test_post_api.py` 的 integration 验证并记录结果；公开演示 API 返回 201 不证明数据真实持久化。不要笼统承诺全部 integration 通过：其中含故意失败用例，且部分旧请求尚未设置 timeout，正式保留为验收项前应整理并加超时。

### D. 提交内容与同步（必须）

- 检查源码、配置、报告及暂存差异中的凭证、个人数据和机器路径；假 Key 测试字符串与真实凭证分开判断。脱敏代码或 `.gitignore` 不能替代检查。
- 按第 2 节显式选择路径暂存；不要直接上传整个工作目录。当前 AM 文件需重新暂存最终版本。
- 检查 `git status --short`、`git diff --cached --stat`、`git diff --cached --check` 和完整暂存差异；确认没有环境、IDE、私人配置或嵌套仓库条目。
- 创建提交后记录提交 SHA；配置真实仓库地址并推送。到 GitHub 核对该 SHA、文件与 README；记录 public/private，私有仓库需确认面试官的访问方式。
- 从远端重新 clone 到干净目录，重复 A/B（声称当前真实 API 可用则重复 C），验证没有依赖本机未上传文件。完成后才标为“远端已同步且可复现”。

可以先上传明确标记为 WIP/未复现的版本保存进度，但不能把这种上传表述为验证通过或可运行交付。

## 5. 简历怎么写才真实

| 表述 | 当前是否适用 | 条件或改写 |
| --- | --- | --- |
| “ApiPilot 接口测试学习项目（本地阶段）” | 可以 | 放在个人/学习项目经历，不编造企业实习经历 |
| “项目包含 requests GET/POST、JSON 参数化数据、状态码/字段断言及结果汇总” | 可以描述项目事实 | 不自动改写为本人独立设计或熟练掌握 |
| “2026-10-10 两条公开 GET 的 CLI 验收记录均为 PASS” | 可作为历史项目证据 | 标注日期及来源，不扩展为全部接口或当前复核通过 |
| “已同步至 GitHub” | 暂不可以 | 真实推送并核对远端提交及文件后可写；private 不等于公开 |
| “GitHub 公开项目，可在线查看” | 暂不可以 | 仓库实际为 public，且目标读者无需账号授权即可访问 |
| “全部测试通过 / 持续集成通过” | 暂不可以 | 新环境实测并交代排除/预期失败；CI 需要真实 workflow 运行记录 |
| “真实 POST 已验证 / AI 已接入并验证” | 暂不可以 | 分别补真实服务验收，不能以 Mock 或代码存在代替 |
| “独立搭建 / 熟练掌握 pytest、requests、自动化框架” | 证据不足 | 需本人能解释、修改、排错并完成相近任务；上传或通过测试都不证明掌握 |
| “Python 测试平台已上线” | 暂不可以 | 私有浏览器 JavaScript 演示不等于 Python 后端部署 |
| “提升效率 X% / 发现 X 个真实缺陷 / 生产级框架” | 证据不足 | 需真实基线、可核查缺陷与相应使用记录 |

可用的保守表述：

> ApiPilot｜接口测试学习项目（本地阶段）：围绕公开 API 进行测试练习，项目包含 GET/POST 请求封装、JSON 用例参数化、状态码与响应字段断言及结果汇总；保留两条真实 GET 的历史验收记录。代码尚未同步至 GitHub，当前环境待重新验证。

若相关练习主要由 AI 或他人完成，应把“进行测试练习”进一步改为“借助 AI 辅助学习”，并只增加本人实际完成的操作。若用户未亲自执行历史验收，不写成“本人完成真实 GET 验收”。

面试前至少本人完成：解释一次请求到断言的链路；独立新增一条 JSON 用例及匹配断言；制造并定位一次 FAIL 和一次 ERROR；解释参数化、Mock、integration 与 PENDING 的区别。完成这些可以增加具体经历描述，仍不宜直接用“精通”。

## 6. 本次实际完成与未完成

- 已完成：文件、Git 状态、配置与历史报告核对；现有差异的空白检查；新增本清单。
- 已尝试但未完成：pytest、CLI help、依赖检查，均因原虚拟环境解释器缺失而未启动成功。
- 尚未完成：新环境安装与运行、真实接口复核、完整提交内容敏感信息审查、提交/推送、远端可见性核对与远端 clone 复现。
- 本次未修改业务代码、历史报告或 Git 暂存内容，也未创建仓库或上传任何文件。
