请根据sources内当前有效政策，核对全部CSV分片并交付可复现的业务报表。旧政策只是历史背景。只用Python标准库，不得硬编码输出；请创建reconcile_data.py，使 python reconcile_data.py --input-dir sources --output-dir output 能从输入重新生成全部产物。
产物：output/summary.csv，字段顺序region,currency,record_count,units,gross,refund,net，按region再currency的Unicode顺序排序，金额两位；output/audit.json，包含policy_id、raw_rows、unique_records、duplicate_or_superseded_rows、void_records、invalid_records（按record_id排序的ID列表）、included_records；output/report.md解释采用哪版政策、为何不能跨币种加总，并引用policy-2026.txt及至少两个CSV来源。
金额和去重语义以当前政策为准。请运行脚本，并独立核对各组净额与审计数量，不要只写计算建议。
