修复本目录的 Python 订单对账工具。它将被用于批处理，必须同时保留 import API 和命令行入口；不是只生成示例结果。
交付：ledger/core.py 的 reconcile(events, cutoff=None)、ledger/io.py 的 read_events(path)、python -m ledger INPUT.csv [--cutoff ISO] [--output PATH]，并在 CHANGELOG.md 简述改动和验证。
只用标准库。不得改变这里规定的输出接口；可修改实现并增加自己的测试。test_public.py 是可见冒烟测试，最终有独立验收。

事件字段：event_id,revision,order_id,type,amount,currency,at。所有输入时间合法且有时区，revision是正整数，相同id相同revision内容相同。CSV须支持引号、Unicode和BOM。
1. 若有cutoff，先按UTC时间保留at<=cutoff的事件，再按event_id仅保留最大revision；重复事件不能重复记账。最终按UTC时间、event_id排序执行，不得按输入顺序或时间字符串排序。
2. 金额用十进制，在每个事件入账前按ROUND_HALF_UP保留两位。禁止浮点误差和跨货币合并。
3. create建立订单限额；重复create拒绝。capture累计不能超过原限额，refund累计不能超过已capture金额，非法事件不能部分入账；退款不会释放capture的原限额。
4. void只允许captured==refunded时成功；成功后capture/refund/void均拒绝。create金额允许0。
5. 按以下顺序确定唯一拒绝原因：negative_amount；create分支duplicate_order；非create分支missing_order、currency_mismatch、unknown_type、voided_order，最后操作特定的over_capture、over_refund、outstanding_capture。
6. 每单状态优先顺序：void；captured>0且净额0为refunded；captured==limit且refunded==0且captured>0为paid；captured>0为partial；否则open。
7. 返回 {"orders":[{"order_id":...,"currency":...,"captured":"0.00","refunded":"0.00","net":"0.00","status":...}],"rejected":[{"event_id":...,"reason":...}],"totals":[{"currency":...,"captured":"0.00","refunded":"0.00","net":"0.00"}]}。orders按order_id排序，totals按currency排序，rejected按执行发生顺序。totals包括所有已建立订单（含void和零额）。金额均为两位小数字符串。
8. API不修改输入。CLI将唯一JSON结果写stdout或--output，诊断不可混入stdout；--output父目录不存在时创建。
请真实修改并测试代码，不要只给建议。
