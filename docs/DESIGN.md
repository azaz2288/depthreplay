# 设计与正确性边界

标准化CSV seq,time_ms,action,order_id,side,price_ticks,quantity。A新增唯一live ID与B/S价格数量；C全撤，side=N price/qty=0；T maker execution，side/price匹配且qty不超过订单，须最优价格。固定整数tick/量，价量1..1e9，最大100万live orders和100万事件。序号从1连续，非负时间不回退，CSV无quoted语法。拒绝交叉簿/缺序/未知订单/超量/错误价位。不会撮合，不校验FIFO同价优先或hidden liquidity，不连接交易所。

unordered_map<ID,Order>索引订单；两侧map<price,aggregate_qty>维护深度。新增/减量O(log L)，查ID均摊O(1)；top5每步固定范围遍历。每事件输出最优价/量/top5/订单数。输入错则取消临时报告，不发布部分结果；临时输出同目录hard-link create-only发布，目的已存在/不支持hardlink失败关闭。输出flush但无fsync，不宣称断电持久；输入同时改变未做快照绑定，先复制稳定输入。

Python快照integer/schema/book invariant校验，缺一侧不评估。用最优量imbalance预测horizon_ms后第一可观察mid变化（不是收益率/利润）。前70%时间训练，跨测试首时间的标签清除，训练均值和ridge只从训练段拟合。留出MAE与训练均值baseline、种子固定的circular moving block bootstrap描述区间。相邻标签重叠、多次模型选择不纠偏。快照SHA绑定解析的同份bytes；报告不含原始订单ID。独立Python参考每事件全订单重算价量，与C++5000随机事件结果逐项一致。

工具本机官方Zig0.13.0 c++编译，CI使用Windows MSVC/Linux GCC CMake，两种编译器不假定benchmark可比。生成器是合成maker feed，无真实交易收益。
