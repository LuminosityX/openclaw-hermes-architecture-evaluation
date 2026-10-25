# 任务W2：原子批量状态变更
在queueboard中实现model.can_transition与service.transition_many(store, ids, target)。
合法状态为todo、doing、done；合法变更为todo→doing、doing→todo、doing→done及合法状态自身；done不能退回。
ids须为list或tuple且元素均为字符串，否则ValueError；未知target为ValueError；未知id为KeyError。
重复id按首次出现去重；结果按去重后的请求顺序返回；空ids返回[]（仍需校验target）。
先校验整批，再写入：任何id或状态不合法都不能改变任何原记录。只更新status，保留title等其他字段。
保持TaskStore公开接口和已有测试，增加自己的测试并运行，提交实现与验证说明。不需要联网或第三方依赖。
