# OpenClaw / Hermes 非功能实测

固定源码与工具链沿用 `/root/output/openclaw-hermes-benchmark-20261022`。新实验独立使用本目录下的状态、工作区、日志和仅监听127.0.0.1的HTTP服务。没有修改框架源码或用户的真实网关。

真实模型：deepseek-flash。密钥由已有安全配置读取，仅在转发进程内使用，不写入本目录。代理向真实DeepSeek转发；429/503实验只在指定请求前返回一次受控错误。转发记录只保存请求内容、用量及时间，不保存请求头或密钥。

运行顺序：`scripts/start_services.py`，`scripts/run_http.py`，`scripts/run_matched_tools.py`。两边命令权限对齐后的文件任务以 `results/tool-matched-runs.json` 为准；最初权限未对齐的数据不进入比较。

命令控制实验分别运行 `timeout_openclaw.mjs`、`timeout_hermes.py`；使用真实原生命令工具，启动父子进程并持续写入活动标记，时限1秒。独立检查存活及标记变化，仅清理本实验残留进程。

MCP实验分别运行 `mcp_openclaw.mjs`、`mcp_hermes.py`。同一个实际stdio服务进程，测量新连接至首次工具完成的等待；7种凭证均为合成测试字符串。两边都过滤成功，作为相同结果留存。

备份比较使用 `runtime/backup-files-openclaw` 与 `runtime/backup-files-hermes` 的最小配置和相同64个文件（2 MiB）；`NF_BACKUP_FILES=1` 分别运行两个备份脚本。OpenClaw显式包含工作区，恢复至新staging目录；Hermes导入到独立新home。逐文件SHA校验，未把成功退出当作恢复完整。较早的不同会话状态备份、未包含工作区的试跑均不采用。

`scripts/summarize.py` 汇总逐条原始证据，验收后生成Notion稿与CSV。报告环境运行 `scripts/render.py` 导出PNG/SVG/PDF柱状图及网页。性能测量按顺序执行，后续分析与绘图不再触发付费模型。

范围：本轮9个维度的限定机制；不包含真实IM、进程崩溃自动续跑、插件升级或跨操作系统迁移。HTTP短回复各3例，权限对齐的文件任务各3例，故障类型各1例，4并发各2批，命令时限及MCP各5例，文件备份恢复各3例。结果为本机固定源码运行环境的小样本，不作为发行包总体资源或生产SLA。

原始provider审计、网关数据库及完整备份留在实验机用于复核；可下载归档不包含runtime、真实密钥、原生数据库、机器身份或备份镜像。
