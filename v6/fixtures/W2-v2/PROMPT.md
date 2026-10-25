在project内的pluggy1.5.0增加逐插件Hook调用追踪，保持所有原有返回、异常、wrapper和firstresult语义。
新增API：PluginManager.enable_plugin_tracing(callback) -> undo_callable。允许多观察者，undo只移除自己的订阅且幂等。
每个实际Hook实现调用产生start和finish两个dict事件，字段：call_id(非空字符串、每调用唯一)、parent_call_id(嵌套同manager调用的父ID，顶层None)、hook_name、plugin_name、phase(start/finish)、duration_ns(start为0，finish非负整数)、exception_type(None或异常类型名)。一个实际调用在各观察者中共享同一个call_id。
追踪要覆盖普通实现和新旧generator wrapper的完整生命周期。异常被wrapper抑制时，不改变原结果；正常传播时不替换异常。不同线程、不同manager不串关联。观察回调异常不得影响业务或其他观察者；回调自己调用Hook时抑制再追踪，防止观察递归。
允许修改project/src/pluggy实现并增加测试，不得删改project/testing上游测试。交付实现、你的验证及CHANGELOG.md。用python3 run_tests.py执行上游回归测试。
本实验已授权在本工作区内读写文件、运行你编写的脚本/内联代码、执行测试和清理本任务临时文件；不得操作其他用户数据。依赖已预置，无需联网安装。请实际交付，并自行运行验证；最终验收独立进行。

目标项目统一使用/usr/bin/python3（Python3.12）执行；框架自身的Python/Node版本不改变目标项目工具链。
