原生 Windows 本地验证包（OpenClaw / Hermes）

本包在 Linux 准备，尚未在你的 Windows 上执行，不代表任何 Windows 项目已经通过。
适用：Windows 10/11，x64 或 ARM64，PowerShell；开始前实验所在盘至少空闲 12 GiB。
需要能下载 Node.js、npm、GitHub 和 Python 包；不需要公网 IP、远程登录或模型 API 密钥。

1. 解压完整文件夹。
2. 在解压目录打开 PowerShell，运行：

   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\Run-Windows.ps1"

   Bypass 只用于这个新建的 PowerShell 进程，不修改系统或用户的持久执行策略。
   默认在系统临时目录创建一个 och-xxxxxxxx 实验目录。也可通过 -ExperimentRoot 指定一个不存在的新目录。
3. 结束或遇到准备错误后，脚本会显示 windows-results.zip 的位置；将这个结果包发回本线程。

实际检查：两个固定版本，各 3 份独立配置与状态；调用原生文件工具写入含中文和 emoji 的文件；关闭客户端后用另一个原生进程读取；检查原生数据库仍保留前一任务的用户记录。
模型端是仅绑定本机回环地址的固定协议服务，真实执行由产品完成，付费模型调用为 0。
这次补充覆盖原生 Windows CLI，不声称测完 Windows GUI、Gateway、后台服务或 Linux 到 Windows 的全状态迁移。
安装/网络/脚本失败需要审阅日志，不能直接写成产品“弱”。

固定版本：OpenClaw 2026.10.6（fe06181）；Hermes 0.22.5（bf0203a）；Node 24.22.1。
下载地址、SHA256 和源安装脚本校验值见 pins.json；不读取已有 Agent 配置或密钥，不修改用户 PATH，不注册后台服务。
依赖每个产品安装一份，三个用例共享，避免重复复制完整环境；空间低于 6 GiB 时不再启动新阶段/用例。
回传包只包含小型原生状态、输入输出、日志和清单，排除安装依赖与缓存。
回传完成后，可删除脚本打印的整个实验目录回收空间；不要删除目录之外的其他内容。
