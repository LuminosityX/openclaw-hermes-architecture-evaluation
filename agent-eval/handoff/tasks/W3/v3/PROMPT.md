# 任务W3：数据清洗与汇总
读取input.csv，输出output/clean.csv和output/summary.json。可编写脚本，不需要联网。
对所有字段先去首尾空白。有效行要求：id非空；region为east/north/west之一；quantity为仅含数字且>=1的整数；unit_price为非负十进制、恰好两位小数。
先校验有效性，再按id保留首个有效记录。无效行计invalid_rows；后续有效重复id计duplicate_rows。
clean.csv保持原有效行顺序，列顺序id,region,quantity,unit_price；quantity规范为十进制整数，价格规范为两位小数。
summary.json仅包含以下字段：input_rows、kept_rows、invalid_rows、duplicate_rows、total_quantity、total_amount_cents、by_region。
金额用整数分计算quantity×unit_price；by_region必须含east/north/west，每项仅包含字段rows、quantity、amount_cents（没有数据也保留0）。
提交输出文件及简短核验说明。不要修改input.csv。只统计本输入文件的数据。
