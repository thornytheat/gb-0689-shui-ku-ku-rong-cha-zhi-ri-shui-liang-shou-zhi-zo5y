# 深度登记 水库库容插值与日水量收支

- 规模：中型
- 核心规则：单调水位库容曲线分段线性插值；流量梯形积分；缺口超限不插补，日边界拆分且收支误差显式归因
- 使用者与工作流：水库调度数据员；采信水位流量日志，复核日库容变化与入出库偏差

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 测站采信 | 采信水位流量与来源 | `/api/m1` | `app/modules/m1_receive/rules.py` `app/modules/m1_receive/service.py` | `tests/test_m1_receive.py` |
| M2 曲线校核 | 校验曲线及测次冲突 | `/api/m2` | `app/modules/m2_curve/rules.py` `app/modules/m2_curve/service.py` | `tests/test_m2_curve.py` |
| M3 流量积分 | 梯形积分并定位缺口 | `/api/m3` | `app/modules/m3_integrate/rules.py` `app/modules/m3_integrate/service.py` | `tests/test_m3_integrate.py` |
| M4 库容换算 | 按曲线分段换算库容 | `/api/m4` | `app/modules/m4_storage/rules.py` `app/modules/m4_storage/service.py` | `tests/test_m4_storage.py` |
| M5 日收支 | 跨午夜切分日水量账 | `/api/m5` | `app/modules/m5_budget/rules.py` `app/modules/m5_budget/service.py` | `tests/test_m5_budget.py` |
| M6 异常复核 | 按缺测优先裁决超差 | `/api/m6` | `app/modules/m6_review/rules.py` `app/modules/m6_review/service.py` | `tests/test_m6_review.py` |
| M7 重算留痕 | 核对总积分与重算水位 | `/api/m7` | `app/modules/m7_trace/rules.py` `app/modules/m7_trace/service.py` | `tests/test_m7_trace.py` |
| LC 站码沿革 | 换号并行核定与日账续算 | `/api/lineage` `/lineage` | `app/lineage/rules.py` `app/lineage/service.py` `app/lineage/store.py` | `tests/test_lineage_rules.py` `tests/test_lineage_store.py` |

## 站码沿革陷阱（LC）

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| LC-01 | 旧码新码并行两班 | 全按对照表合并，并行时段算两遍 | 同刻逐刻去重，停用前采旧码，去重留痕 raw_code | `app/lineage/rules.py::canonical_observations` | `tests/test_lineage_rules.py::test_decided_window_dedupes_to_one_series` |
| LC-02 | 迁移单未写旧码停用时刻 | 卡死在新码启用点，换号前后断成缺测 | 并行窗口挂起待裁定，两侧确认段照算并标缺测，不硬切 | `app/lineage/rules.py::build_segments` | `tests/test_lineage_rules.py::test_pending_window_is_blocked_when_deactivate_missing` |
| LC-03 | 同刻新旧水文值矛盾 | 静默采信其一 | 整窗挂起，两码观测全部 suspended 不进日账 | `app/lineage/rules.py::_adjudicate_parallel` | `tests/test_lineage_rules.py::test_conflicting_parallel_values_block_window` |
| LC-04 | 同一换号反复重跑 | 每次新增重复日账 | 指纹幂等+日账 (site,date) 唯一键，复用版本 | `app/lineage/store.py` | `tests/test_lineage_store.py::test_same_renumber_rerun_is_idempotent_no_duplicate` |
| LC-05 | 核定失败覆盖已确认沿革 | 已确认段被回退 | 失败存版本0挂起，旧版保留，从水位线续算不回退 | `app/lineage/store.py::resume` | `tests/test_lineage_store.py::test_resume_from_pending_promotes_version_and_writes_ledger` |
| LC-06 | 跨换号串号续算 | 把别的站数据并进当前日账 | 指纹校验不一致返回 FINGERPRINT 422 | `app/lineage/store.py::resume` | `tests/test_lineage_store.py::test_resume_rejects_cross_fingerprint` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | GB18030测站 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m1_receive/rules.py` | `tests/test_m1_receive.py::test_legacy_encoding` |
| TRAP-06 | 全角流量 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m2_curve/rules.py` | `tests/test_m2_curve.py::test_fullwidth` |
| TRAP-07 | 未知水位 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m2_curve/rules.py` | `tests/test_m2_curve.py::test_sentinel` |
| TRAP-10 | 小数插值 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m4_storage/rules.py` | `tests/test_m4_storage.py::test_decimal_precision` |
| TRAP-13 | 缺口和乱序 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m3_integrate/rules.py` | `tests/test_m3_integrate.py::test_real_late_point_retained` |
| TRAP-14 | 同刻水文矛盾 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m2_curve/rules.py` | `tests/test_m2_curve.py::test_real_conflict` |
| TRAP-15 | 升每秒换算 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m2_curve/rules.py` | `tests/test_m2_curve.py::test_unit_conversion` |
| TRAP-23 | 午夜切分 | 静默填补或算错 | 明确隔离和守恒 | `app/modules/m5_budget/rules.py` | `tests/test_m5_budget.py::test_midnight_split` |

## 对账规则

输入逻辑行数 = 采信行数 + 隔离行数；空行单列。每条重复、冲突、超限、缺失均保留原始行号与原因码。计算阶段的输出数量可聚合，原始采信records始终保留，业务平衡另按模块给出的重量、时长、电量或座席数量核对。
相同输入摘要、规则版本、参数产生相同批次ID。运行原子插入SQLite；复核使用整数版本乐观锁。

## 已知不覆盖

库容曲线采用线性分段，不作范围外推；流量与水位相邻点间线性变化。未建蒸发降雨及地下渗漏模型，收支差保留待人工归因。
