# 运行维护

主服务端口与Compose保持一致。数据保存在records命名卷，应用代码不需要写入权限。

```sh
docker compose logs --tail=80 app
docker compose restart app
docker compose exec -T app pytest -q
docker compose down --remove-orphans
```

健康检查GET /health。失败输入返回原因码，结构性错误422，过大文件413，陈旧复核409。
文件内容最大4MB。批次先计算再原子保存，失败不留半条记录。证据CSV按原始行号定位。

## 站码沿革换号核定

独立于七步主管线，入口页 `/lineage`，接口 `POST /api/lineage`（JSON 或 multipart 上传观测CSV+迁移单CSV）。挂起后补登停用时刻，凭返回的 `fingerprint` 调 `POST /api/lineage/resume/<fingerprint>` 从已确认段续算。

- 迁移单 `deactivate_at` 留空表示停用时刻未登记：并行窗口判“待人工裁定”，该窗观测挂起，日账不双算；补登后再续算。
- `GET /api/lineage/<fingerprint>/evidence.csv` 导出沿革段、并行窗口与一条日账，含原始CSV行号与原始站码。
- 同一换号（同指纹）重跑复用既有版本，日账按 (逻辑站,日期) 唯一，不新增重复；跨换号指纹续算返回422 FINGERPRINT。
- 核定失败保留旧版沿革（版本0挂起），已确认段水位线 `confirmed_watermark` 不回退；`GET /api/lineage` 查沿革版本历史。
- 沿革表 `lineage_versions`、`lineage_ledgers` 与主管线 `runs` 同库存放，删除 records 卷会一并清空。
