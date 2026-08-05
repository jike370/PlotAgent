# PlotAgent 最小 Beta 控制面

本目录说明 `src/plotagent/control_plane/` 的独立 W8/M6 切片。它只负责邀请兑换、长期
DeviceCredential、凭据校验/撤销、built-in model proxy、InviteGrant 共享额度与
`client_run_id` 幂等；不部署真实云，也不包含账号、项目/图表/原始数据存储、同步、custom provider
计费、CloudConfig、更新、analytics、诊断上传或 reserve/settle/reconcile。

## 运行

先安装 Python 开发环境：

```powershell
python -m pip install -e ".[dev]"
```

运行入口要求三个显式环境配置。实际 pepper 应由部署环境的 secret manager 注入，不要提交到仓库或
放入可共享的命令历史：

```powershell
$env:PLOTAGENT_CONTROL_PLANE_DATABASE_PATH = "D:\PlotAgentBeta\control-plane.sqlite3"
$env:PLOTAGENT_CONTROL_PLANE_SECRET_PEPPER = "<at-least-32-byte-service-secret>"
$env:PLOTAGENT_CONTROL_PLANE_DEPLOYED_MODEL_PROFILES = '{"builtin-beta":{"deployment_id":"provider-deployment","quota_unit":1}}'
python -m plotagent.control_plane
```

可选配置包括 `HOST`（默认 `127.0.0.1`）、`PORT`（默认 `8000`）、
`PROVIDER_TIMEOUT_SECONDS`（默认 30）、`IDEMPOTENCY_RESPONSE_TTL_SECONDS`（默认 86400，允许
60–604800 且必须大于 provider timeout）和 `SQLITE_BUSY_TIMEOUT_MS`（默认 10000）。非法配置只报告
字段名，不回显配置值。

入口默认使用 `UnavailableProviderAdapter`，因此不会误连真实上游。真正部署时需在部署方 ASGI 包装中
调用 `create_app(settings, provider=adapter)` 注入实现；平台 provider key 由 adapter 自己持有，不能进入
请求、SQLite、日志或客户端 DeviceCredential。邀请码由受信 operator 通过
`ControlPlaneStore.create_invite_grant()` 写入，plaintext secret 只在创建/发放时存在，数据库只保存
版本化 keyed hash。`revoke_grant()` 和 `block_device()` 同样是 operator hook，不开放账号或 admin
profile API。

## API

| Method | Path | 行为 |
| --- | --- | --- |
| `GET` | `/healthz` | 本地健康与协议版本，不访问 provider |
| `POST` | `/v1/invites/redeem` | 同一 grant 不限设备兑换；返回一次长期凭据 |
| `POST` | `/v1/credentials/verify` | Bearer 凭据、grant 与共享额度快照 |
| `DELETE` | `/v1/credentials/current` | 撤销当前长期凭据 |
| `GET` | `/v1/quota` | 服务端权威 InviteGrant 共享计数 |
| `POST` | `/v1/model-runs` | built-in 单次结构化请求、原子扣减和幂等结果 |
| `GET` | `/v1/model-runs/{client_run_id}` | 查询同 grant 的既有 run，不调用上游 |

服务没有 custom provider、项目、更新、analytics 或 diagnostic 端点。顶层未知字段会被拒绝，因此不能把
`provider_type=custom` 路由进 built-in 账本。

## 扣减、重复、离线与 timeout

- SQLite 以 `BEGIN IMMEDIATE` 原子完成既有 run 检查、grant/device/profile/quota 校验、run 插入与
  一次固定扣减。事务失败不留下 run 或扣减。
- 同一 `(invite_id, client_run_id)` 和同一请求返回已有状态/短期结果；不同 context、profile 或 payload
  keyed fingerprint 返回 `IDEMPOTENCY_CONFLICT`。重复请求永不再次调用 adapter，也不再次扣减。
- 首次接受后不释放额度。provider timeout 或进程无法证明 accepted/invoking run 的结果时保存
  `RUN_OUTCOME_UNKNOWN`；明确 adapter 不可用保存 `PROVIDER_UNAVAILABLE`。两者的重复请求都只返回
  已存错误。
- 若 DNS/TLS/连接错误使请求根本未到达控制面，服务端没有记录也没有扣减；客户端最多重试两次并必须
  复用相同 `client_run_id`。确定性 4xx 不自动重试。
- 正在处理的重复请求返回 HTTP 202 与同一 run 状态。完成响应默认保留 24 小时，到期后只保留 run
  元数据并返回 `RUN_OUTCOME_UNKNOWN`，绝不以新 ID 重放。
- `QUOTA_EXHAUSTED`、grant/device 撤销或云不可达只影响 built-in API；custom provider 和所有本地能力
  不访问本服务，也不消耗额度。

## 隐私与测试

installation ID 只验证随机 UUID 形态，不写入数据库或日志；schema 中没有账号、email、profile、硬件
指纹或设备数限制。邀请 secret、DeviceCredential 与请求 payload 都不明文持久化；payload 仅形成 keyed
fingerprint，短期 response body 与普通日志分离。运行入口关闭 Uvicorn access log，应用日志只含 run、
invite/device 伪名、profile、quota unit、幂等状态和稳定错误。验证错误与未知 adapter 异常统一净化，
不附带请求值或 traceback。

```powershell
python -m pytest -q tests/control_plane
python -m ruff check src/plotagent/control_plane tests/control_plane
python -m mypy src/plotagent/control_plane
```

测试使用注入 adapter，不访问真实网络，并包含多设备共享、撤销/过期、quota/custom 边界、timeout/重启、
日志与错误禁止字段扫描，以及 SQLite 并发不超扣/不双扣。
