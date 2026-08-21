# Signal Hunt — 完整指南

> 语言：[English](GUIDE.md) · [Русский](GUIDE.ru.md) · [Español](GUIDE.es.md) · [Français](GUIDE.fr.md) · **中文**
> 规则：[English](RULES.md) · [Русский](RULES.ru.md) · [Español](RULES.es.md) · [Français](RULES.fr.md) · [中文](RULES.zh.md)

## 1. Signal Hunt 是什么

Signal Hunt 是一款联邦原生调查游戏，**同时也是教育实验室**。每个回合都来自普通
AIMarket Hub 的真实快照：已索引的外部 capabilities、来源分布、实际价格、签名身份
和已保存历史。玩家检查证据、选择诊断并声明置信度。

请把它理解为 **包在游戏外壳里的实验课**：循环有趣，但课程是实时联邦素养——
阅读 Hub 遥测、为证据付代价、用 Brier 校准置信度、核验密码学承诺，并观察联邦
增长、peer 加入/离开与延迟天气如何改变可用诊断。

它不是模拟仪表盘。如果 Hub 无法被观测，游戏会明确返回不可用状态，而不会
替换为 fixture。缺失的历史或价格会继续显示为缺失。

### 学习成果

若干回合后，认真的玩家应当能够：

1. 用测量来源解释 Hub 观测，而不是叙事臆测。
2. 用已发布的 evidence factor 在证据成本与得分之间取舍。
3. 给出经得起 Brier 的置信度，而不是虚张声势。
4. 用盐值、承诺与返回操作数重算裁决。
5. 把检测器类别（隔离、消失、peer 变动、延迟天气、集中……）与联邦增长下的真实目录、
   名册与延迟动态联系起来。

## 2. 服务器组成

生产部署包含 PostgreSQL、普通 AIMarket Hub、Signal Hunt 引擎和 Caddy TLS
入口。一次性 bootstrap 注册五个本地 capabilities：

| Capability | 用途 |
|---|---|
| `signal.case@v1` | 返回当前不可变调查 |
| `signal.evidence@v1` | 揭示一个已承诺的证据块 |
| `signal.submit@v1` | 验证诊断并计算得分 |
| `signal.leaderboard@v1` | 返回仅由持久化裁决生成的排行榜 |
| `signal.heroes@v1` | 返回自愿公开、带签名的英雄里程碑 |

通用随机性不会在本地重写。可用时，引擎通过自己的 Hub 发现远程
`sortes.draw@v1`，并保存路由、来源 Hub、receipt nonce 和 result hash。失败会
记录为 `unavailable`，绝不会伪装成成功调用。

## 3. 玩家流程

1. **观测。** 首屏展示真实 Hub、来源、capability 数量、manifest 延迟、观测 ID
   和 state hash。
2. **调查。** 可查看六类证据：来源分布、历史变化、实际价格、peer 名册、延迟面和来源 (provenance)。
3. **决策。** 从四个诊断中选择一个，可选回答第二道锁（follow-up），并设置 25–100% 置信度。
4. **验证。** 服务器公开盐值、检查 commitment、叠加 follow-up 加成与已锁定的 PRIME 倍率，
   保存不可变裁决，并显示下一场窗口的悬念提示。
5. **成长。** 积分决定等级；日连续、周赛护照与明确条件解锁装饰性遗物。强轨道可在
   opt-in 后一键广播。不会铸造资产，也不承诺金融价值。

公式与白话互动规则见[完整规则](RULES.zh.md) §6–7。

## 4. 真实性与来源

每次观测保存 upstream 生成时间、本地观测时间、Hub URL 与 signer key、各来源
数量、价格汇总、请求状态和规范 state hash。回合引用该不可变观测，之后的新数据
不会改变已生成证据。

正确诊断来自公开的确定性阈值。回合公开前，引擎生成随机盐并发布：

```text
SHA256(round_id:answer_code:answer_salt)
```

答案与盐值仅在裁决时公开。任何审查者都能重算 commitment 和所有评分操作数。

## 5. 身份、隐私与英雄

默认匿名。浏览器获取不透明的签名 session token，并只在设备本地保存。无需钱包、
邮箱或社交登录；游戏表不保存原始 IP。

公开英雄功能默认关闭，明确 opt-in 后也只影响未来里程碑。签名 feed 包含呼号、
聚合验证统计、奖励代码和证明引用，不包含 session token、IP 或私人证据。

DIOSCURI 主动拉取 feed，并用运营方预先固定的 Ed25519 key 验证。Discord 与 X
分别保存投递状态；一个平台重试不会导致另一个重复发布。游戏不保存社交凭据。

## 6. HTTP API

| 方法 | 路由 | 访问方式 |
|---|---|---|
| `POST` | `/api/v1/session` | 公开 |
| `GET`, `PUT` | `/api/v1/profile` | bearer session |
| `GET` | `/api/v1/rounds/live` | bearer session |
| `GET` | `/api/v1/rounds/{id}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/evidence/{evidence}` | bearer session |
| `POST` | `/api/v1/rounds/{id}/submit` | bearer session |
| `POST` | `/api/v1/rounds/{id}/broadcast` | bearer session |
| `GET` | `/api/v1/leaderboard` | 公开 |
| `GET` | `/api/v1/leaderboard/weekly` | 公开 |
| `GET` | `/api/v1/heroes/feed` | 公开、payload 有签名 |
| `GET` | `/provider/public-key` | 公开 |
| `POST` | `/provider/invoke` | AIMarket provider 接口 |

## 7. 本地开发

先启动 AIMarket Hub，再启动后端和前端：

```bash
cd signal-hunt
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
SIGNAL_HUNT_HUB_URL=http://127.0.0.1:9183 .venv/bin/python -m signal_hunt.main
```

```bash
cd signal-hunt/frontend
npm ci
npm run dev
```

若配置的 Hub 无法提供有效实时 manifest，页面会明确失败，不生成演示回合。

## 8. 生产部署

1. 将 DNS A/AAAA 指向新服务器，并开放 TCP 80/443 与 UDP 443。
2. 将 `.env.example` 复制为 `.env`。
3. 分别生成 `AIMARKET_ADMIN_TOKEN` 和 `POSTGRES_PASSWORD`。
4. 通过独立渠道验证每个 seed public key。
5. 运行 `scripts/deploy.sh`。
6. 在可信运营机器上运行 `scripts/register-upstream.sh`，让现有 Hub announce、
   approve 并 crawl 新 Hub。
7. 运行 `scripts/verify.sh https://<signal-hunt-domain>`。

只有 Caddy 暴露公网端口。Hub/provider key 必须与 PostgreSQL 和游戏状态一起备份。

## 9. 运维与失败语义

- `503 federation_unavailable`：无法生成有效实时回合。
- baseline 为 `null`：测量历史不足，不代表变化为零。
- `federation_assist.status=unavailable`：诚实降级，不声称执行了远程 VRF。
- 重复提交返回已存裁决，不会再生成奖励。
- 丢失签名 key 会改变身份，必须显式恢复信任。
- Relay 错误显示在 DIOSCURI `/health`，但不阻塞游戏。

## 10. 验证与贡献

```bash
cd signal-hunt && pytest -q
cd frontend && npm run build
```

GitHub Actions 会运行 Signal Hunt 的 pytest、前端构建，以及 `docker compose config`。
DIOSCURI hero feed 的签名契约由 monorepo 中 DIOSCURI 包的测试覆盖。项目使用
[MIT License](../LICENSE)。评分、检测优先级或奖励阈值的变更必须同时更新测试和
五种语言规则。
