# 水位与水量定义

id、station为字符串。time含时区，统一UTC，日账在+08:00午夜拆分。level单位m；inflow/outflow单位m3/s或L/s，归一m³/s；空值不等于零。负流量与曲线外水位隔离。
curve为[[水位,库容],...]，水位及库容必须严格递增，库容非负，单位m与m³。只对范围内水位分段线性插值，端点允许。
同站同刻按version最高记录采信，同版不同值全部隔离。重复旧版有独立证据。输入=采信+隔离；原始行号保留。
相邻观测间以梯形积分计算流量体积，超过max_gap_hours则不插补。日界处先线性插出流量与水位，再分别积分及按曲线换算库容。日账是已覆盖时段的收支，覆盖不足24h始终待补测。
日收支差=库容变化-入库+出库，绝对值超过tolerance_m3需复核。缺测优先于超差。无蒸发降雨模型，差额不自动认作漏损。
数值为Decimal字符串，日切与整段积分容许1e-9m³以内十进制除法尾数。规则参数和输入摘要参与幂等ID；批次原子保存，复核版本冲突返回409。

原始到达序小于此前最大事件时刻的测次标记arrival=迟到，仍保留并按事件时间排序积分，迟到不会推进水位回退。

## 站码沿革核定（换号并行）

遥测站换号后旧码与新码并行，日账必须按逻辑站连成一条。独立入口 `/lineage`、`/api/lineage`，不改写 M1–M7 七步主管线。

观测CSV契约：`id,station,code,time,level,inflow,outflow,flow_unit,version`，`code` 为原始站码；迁移单CSV契约：`site,old_code,new_code,activate_at,deactivate_at,note`，`deactivate_at` 留空即“迁移单未写清旧码停用时刻”。

核定产物字段：

- `segments` 沿革段：`site` 逻辑站、`kind`（old_only/new_only/parallel/gap）、`adopted_code` 该段采用站码、`start/end`、`row_lines` 原始CSV行号。
- `parallel_windows` 并行时段：`old_code/new_code`、`start/end`、`decidable`、`state`（可裁定/待人工裁定）、`reason` 裁定依据、两侧行号。
- `canonical` 进日账观测：`station` 统一为逻辑站，`station_code` 为采用码，`raw_code` 保留原始站码，`deduped` 记录被去重的并行观测行号与原码，全程可追溯。
- `suspended` 挂起观测：落在无法裁定并行窗口内，不进日账（杜绝双算与硬切缺测）。
- `budgets` 按逻辑站连成一条的日账；`fingerprint` 换号指纹；`adjudicated` 总裁定结论。

裁定规则：迁移单缺停用时刻，整段并行窗口挂起，仅窗口两侧确认段（前旧码、后新码）入账；补登停用时刻后，并行期同刻新旧水文值一致则逐刻去重（停用前采旧码、停用起采新码），同刻矛盾或停用后旧码仍有观测则窗口挂起。无重叠时在启用点硬切，启用点取新码。

`fingerprint` 仅由逻辑站+新旧码对照+规范化观测摘要决定，排除停用时刻/备注，保证“挂起→补登续算”同一版本线；不同换号指纹必异。日账表 `(fingerprint,site,date)` 唯一，重跑同一换号复用版本、不新增重复日账。核定失败保存为版本0“挂起待裁定”，不覆盖已确认沿革，续算从 `confirmed_watermark` 已确认段水位线推进、不回退；跨指纹续算返回 FINGERPRINT(422)。
