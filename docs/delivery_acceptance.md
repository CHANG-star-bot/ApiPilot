# ApiPilot 首次提交验收

核对日期：2026-10-17（Asia/Shanghai）。

## 交付范围与结论

这是用于测试开发实习准备的个人学习项目，具备最小功能闭环：
读取本地 OpenAPI 和显式测试配置，生成可执行/待补充用例，发送 GET/POST，断言响应，
批量汇总并保存脱敏 JSON 报告。AI 建议模块独立，始终待人工确认，不自动执行。

首次提交包括 Python 源码、测试、依赖清单、安装与学习说明、示例以及注明来源的历史验收记录。
虚拟环境、IDE 文件、本机环境变量和 sites/ 下的独立网页原型不纳入 Python 主仓库。

提交前检查发现 ai_scenario_generator.py 中 strategy 被误写为 strateg y，导致测试收集失败。
本次仅修复该拼写错误，没有扩展功能。

## 当前本地验证

- Python 3.12.4。
- requirements.txt：requests 2.34.2、pytest 9.1.1。
- 命令：`.\.venv\Scripts\python.exe -m pytest -q`。
- 实际结果：302 passed、9 deselected，退出码 0。
- 命令：`.\.venv\Scripts\python.exe -m src.apipilot.cli --help`。
- 实际结果：正常显示参数说明，退出码 0。

离线测试使用 Mock 验证本地逻辑。9 项 integration 默认未执行，其中保留故意失败的学习用例。
本次没有重新调用公开业务接口或大模型。

## 独立环境复现

将待提交的 56 个 Git 暂存文件导出到独立临时目录，新建 Python 3.12.4 虚拟环境，
从 PyPI 安装 requirements.txt 中的固定依赖，没有复用原项目的 .venv。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.apipilot.cli --help
```

实际结果：依赖安装成功；302 passed、9 deselected in 4.06s；CLI 帮助正常，整体退出码 0。
暂存范围检查未发现配置的 AI Key、常见真实令牌或私钥格式，且没有嵌套 Git 仓库条目。
这些检查支持作为个人学习项目建立初始提交，不代表已经部署或完成全部真实接口验收。

## 历史真实记录

- 两条公开 GET 的真实结果见 reports/real_result.json 与 real_acceptance.md。
- 两次真实模型调用及质量问题见 reports/ai_real_acceptance.json 与 ai_real_acceptance.md。

历史报告保留原日期和结果，不当作本次新请求的结果。

## 当前限制

只支持基础 OpenAPI JSON 和 GET/POST，不展开引用，不自动生成业务数据、凭证和预期断言。
AI 的结构化检查不证明任意自然语言或业务语义正确。
尚无持续集成记录、生产部署或性能结论。
旧 main.py 是故意断言失败的学习脚本；正式入口为 CLI。

## 后续迭代

首次提交保存当前真实状态。以后可以继续修改，测试后创建新提交并推送。
不会把此前未提交的开发过程补写成虚构的历史版本。
学习顺序见 learning_guide.md；理解与亲手练习同样属于每阶段的完成标准。
