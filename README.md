# 水库库容插值与日水量收支

使用者：水库调度数据员。采信水位流量日志，复核日库容变化与入出库偏差。

核心规则：单调水位库容曲线分段线性插值；流量梯形积分；缺口超限不插补，日边界拆分且收支误差显式归因。

## 启动

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
docker compose config --quiet
```

浏览器访问 http://localhost:18203 。首页已装载脏样例，可编辑CSV与参数后运行，也可上传文件。七个导航分别对应业务步骤。

## 模块

- M1 测站采信：采信水位流量与来源，入口 `/m/1`、`GET/POST /api/m1`。
- M2 曲线校核：校验曲线及测次冲突，入口 `/m/2`、`GET/POST /api/m2`。
- M3 流量积分：梯形积分并定位缺口，入口 `/m/3`、`GET/POST /api/m3`。
- M4 库容换算：按曲线分段换算库容，入口 `/m/4`、`GET/POST /api/m4`。
- M5 日收支：跨午夜切分日水量账，入口 `/m/5`、`GET/POST /api/m5`。
- M6 异常复核：按缺测优先裁决超差，入口 `/m/6`、`GET/POST /api/m6`。
- M7 重算留痕：核对总积分与重算水位，入口 `/m/7`、`GET/POST /api/m7`。
- LC 站码沿革：换号新旧码并行核定，并行段去重/挂起并把日账按逻辑站连成一条，入口 `/lineage`、`POST /api/lineage`、`POST /api/lineage/resume/<fingerprint>`。

## 演示与复核

1. 运行默认样例，核查隔离原因与业务合计。
2. 修改CSV单元格或参数并重跑，保留行号与输入摘要。
3. 在最后一步复核，旧版本提交返回409。
4. 证据CSV包含采信行和隔离行，重跑相同内容复用批次。

## 数据与目录

`app/modules/` 按业务切分；`sample_data/` 为UTF-8 BOM、GB18030及干净/脏样例；`tests/` 含规则与端到端测试。SQLite保存运行与复核，命名卷records保留重启后的记录。若需从头开始，可先停止服务并在确认不再需要记录后删除该项目records卷。

## 定义与边界

库容曲线采用线性分段，不作范围外推；流量与水位相邻点间线性变化。未建蒸发降雨及地下渗漏模型，收支差保留待人工归因。

详细字段、计算定义与原因码见 `docs/DATA-DICTIONARY.md`，回归证据见 `docs/DEPTH.md`。
