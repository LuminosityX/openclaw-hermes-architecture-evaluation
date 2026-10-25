# 任务W1：分页缺陷修复
修复 pagination.py 的 paginate(items, page, page_size)，保持公开接口和返回字段。
page 从1开始；page和page_size必须是正整数，bool/浮点/字符串均应抛ValueError。
total_pages向上取整，空集合为0；越界页返回空items；has_next仅表示还有非空后续页。
不得修改输入集合；支持list与tuple；返回items为list。
请运行本地测试，可补充自己的测试，提交代码和简短验证说明。不要删除或改写已有公开测试来绕过要求。
不需要联网或安装依赖。验收还包含本工作区外的独立测试。
