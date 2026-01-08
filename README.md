# 🤖 SentinelBot

<div align="center">

**基于 Prometheus 的智能监控告警 Telegram 机器人**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docs.docker.com/compose/)

[功能特性](#-功能特性) • [快速开始](#-快速开始) • [配置指南](#-配置指南) • [使用文档](#-使用文档) • [架构设计](#-架构设计)

</div>

---

## 📖 项目简介

SentinelBot 是一个功能完整的监控告警系统，将 **Prometheus + Alertmanager + Telegram Bot** 完美结合，为运维人员提供：

- 🚀 **秒级告警推送**：从告警触发到手机收到通知仅需 2-5 秒
- 📊 **交互式监控面板**：在 Telegram 中实时查询服务器资源状态
- 🎯 **智能告警路由**：支持按严重程度、项目分组的告警策略
- 🔐 **MFA 验证码**：集成 TOTP 验证码生成功能
- 🌐 **多项目支持**：统一管理多个项目的服务器和数据库

---

## ✨ 功能特性

### 1. 📡 全方位监控

#### 服务器监控（Node Exporter）
- ✅ CPU 使用率（5分钟平均，含趋势箭头）
- ✅ 内存占用（基于 `MemAvailable`，更准确）
- ✅ 磁盘空间（支持多分区，自动识别最紧张分区）
- ✅ 系统负载（Load1 指标）
- ✅ 磁盘 Inode 使用率

#### 数据库监控（CloudWatch Exporter）
- ✅ AWS RDS CPU 利用率
- ✅ 数据库连接数
- ✅ 剩余存储空间
- ✅ 可用内存

### 2. 🚨 智能告警系统

#### 分级告警
| 级别 | 告警类型 | 阈值 | 持续时间 | 重复间隔 |
|------|---------|------|---------|---------|
| 🔴 Critical | 实例宕机 | up == 0 | 10s | 15分钟 |
| 🔴 Critical | CPU 严重 | > 90% | 5分钟 | 30分钟 |
| 🔴 Critical | 内存即将耗尽 | > 95% | 5分钟 | 30分钟 |
| 🟠 Warning | CPU 使用率高 | > 80% | 5分钟 | 2小时 |
| 🟠 Warning | 内存使用率高 | > 85% | 5分钟 | 2小时 |
| 🟠 Warning | 磁盘空间不足 | > 85% | 10分钟 | 2小时 |

#### 告警优化
- ⚡ **宕机告警零延迟**：`group_wait: 0s`，立即推送
- 🛡️ **防刷屏机制**：超过 10 条告警自动折叠
- 🌍 **时间本地化**：UTC 自动转换为北京时间（CST）
- 🔗 **快捷操作**：一键查看节点详情、项目汇总

### 3. 💬 Telegram 交互式界面

#### 主菜单
```
🏠 主菜单
├── 🔐 MFA 验证码
├── 📂 浏览项目服务器
│   ├── 按项目分组查看
│   ├── 查看节点详细指标
│   └── 查看 RDS 数据库状态
├── 📊 查看项目汇总
│   ├── 全部资源
│   └── 仅异常节点
└── 🚨 当前告警
```

#### 节点详情页
- **实时指标**：CPU、内存、磁盘、负载
- **趋势分析**：↗️ 上升 / ↘️ 下降 / ➡️ 平稳
- **磁盘分区**：列出所有挂载点的使用情况
- **一键刷新**：随时获取最新数据

#### MFA 验证码
- **倒计时进度条**：可视化显示剩余时间
- **一键刷新**：无需重新发送命令
- **权限控制**：仅管理员可用

---

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- Telegram 账号
- 被监控服务器需安装 [Node Exporter](https://github.com/prometheus/node_exporter)

### 1. 克隆项目

```bash
git clone https://github.com/7Ese/SentinelBot.git
cd SentinelBot
```

### 2. 配置环境变量

```bash
cp .env.example .env
cp monitoring/.env.example monitoring/.env
```

编辑 `monitoring/.env`，填入你的配置：

```bash
# Telegram Bot Token（从 @BotFather 获取）
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
# 管理员 User ID（向 @userinfobot 发送消息获取）
TELEGRAM_ADMIN_ID=123456789
# 告警推送的群组/频道 ID（将 Bot 加入群组后获取）
TELEGRAM_CHAT_ID=-1001234567890

# MFA 密钥（可选）
MFA_SECRET=YOUR_TOTP_SECRET

# AWS 凭证（如需监控 RDS）
AWS_ACCESS_KEY_ID=YOUR_AWS_ACCESS_KEY_ID_HERE
AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET_ACCESS_KEY_HERE
```

### 3. 配置监控目标

编辑 `monitoring/prometheus/prometheus.yml`：

```yaml
scrape_configs:
  - job_name: 'nodes'
    static_configs:
      - targets:
          - '10.0.1.10:9100'  # 替换为你的服务器 IP
        labels:
          project: 'MyProject'
          role: 'web'
          alias: 'web-server-01'
```

### 4. 启动服务

```bash
./manage.sh start
```

### 5. 验证部署

在 Telegram 中向你的 Bot 发送 `/start`，如果收到欢迎消息，说明部署成功！

访问 Web 界面：
- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Grafana: http://localhost:3000 (默认账号: `admin` / `admin123`)

---

## ⚙️ 配置指南

### 配置被监控服务器

在每台需要监控的服务器上安装 Node Exporter：

```bash
# 下载 Node Exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz
tar -xvf node_exporter-1.7.0.linux-amd64.tar.gz
cd node_exporter-1.7.0.linux-amd64

# 启动服务
./node_exporter &

# 验证（应该能看到指标输出）
curl http://localhost:9100/metrics
```

推荐使用 Systemd 管理：

```bash
sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<EOF
[Unit]
Description=Node Exporter
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/node_exporter
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter
```

### 配置 AWS RDS 监控

1. 确保 AWS 凭证有 CloudWatch 读取权限
2. 编辑 `monitoring/cloudwatch/rds-config.yml`
3. 在 `sentinel/sentinel.py` 中添加你的 RDS 实例：

```python
RDS_INSTANCES: List[Dict[str, str]] = [
    {"id": "my-rds-instance", "project": "MyProject", "alias": "生产数据库"},
]
```

### 自定义告警规则

编辑 `monitoring/prometheus/rules/basic-alerts.yml`：

```yaml
- alert: CustomAlert
  expr: your_prometheus_query > threshold
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "告警摘要"
    description: "详细描述"
```

---

## 📚 使用文档

### 管理脚本

```bash
# 启动所有服务
./manage.sh start

# 停止所有服务
./manage.sh stop

# 重启服务
./manage.sh restart

# 查看服务状态
./manage.sh status

# 查看实时日志
./manage.sh logs
```

### Telegram 命令

| 命令 | 描述 |
|------|------|
| `/start` | 显示主菜单 |
| `/mfa` 或 `/FA` | 获取 MFA 验证码 |

### 交互按钮

所有操作都通过内联按钮完成，无需记忆命令：

1. **浏览项目服务器**：选择项目 → 查看节点列表 → 点击节点查看详情
2. **查看项目汇总**：选择项目 → 查看所有资源或仅异常节点
3. **当前告警**：查看所有 Firing 状态的告警

---

## 🏗️ 架构设计

```
┌─────────────────────┐
│  被监控服务器        │
│  (Node Exporter)    │
│  :9100              │
└──────────┬──────────┘
           │
           │ scrape
           ▼
┌─────────────────────┐      ┌──────────────────┐
│   Prometheus        │─────▶│  Alertmanager    │
│   :9090             │      │  :9093           │
└──────────┬──────────┘      └─────────┬────────┘
           │                           │
           │ query                     │ webhook
           │                           ▼
           │                  ┌──────────────────┐
           │                  │  SentinelBot     │
           │                  │  (Flask:5000)    │
           │                  │  (Telegram)      │
           │                  └─────────┬────────┘
           │                            │
           ▼                            │
┌─────────────────────┐                │
│  Grafana            │                │
│  :3000              │                │
└─────────────────────┘                │
                                       ▼
                              ┌──────────────────┐
                              │  Telegram API    │
                              └──────────────────┘
```

### 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Prometheus | latest | 指标采集与查询 |
| Alertmanager | latest | 告警路由与推送 |
| Grafana | latest | 数据可视化 |
| CloudWatch Exporter | latest | AWS RDS 监控 |
| Python | 3.9+ | Bot 开发语言 |
| python-telegram-bot | 13.15 | Telegram Bot SDK |
| Flask | 2.3.3 | Webhook 服务器 |
| Docker Compose | - | 容器编排 |

---

## 🔧 常见问题

### Q1: Bot 无响应？

检查环境变量是否正确配置：
```bash
cd monitoring
docker-compose logs sentinel-bot
```

### Q2: Prometheus 无法采集指标？

1. 确保服务器防火墙开放 9100 端口
2. 检查 `prometheus.yml` 中的 IP 地址是否正确
3. 手动测试：`curl http://your-server:9100/metrics`

### Q3: 告警没有推送到 Telegram？

1. 检查 Alertmanager 配置：`http://localhost:9093`
2. 确保 Bot 在群组中有发送消息权限
3. 查看 Webhook 日志：`docker-compose logs sentinel-bot`

### Q4: 如何获取 Telegram Chat ID？

1. 将 Bot 加入群组
2. 向群组发送一条消息
3. 访问：`https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. 在返回的 JSON 中找到 `chat.id`

---

## 🎯 未来计划

- [ ] 支持服务发现（Consul / Kubernetes）
- [ ] 接入长期存储（Thanos / VictoriaMetrics）
- [ ] AI 辅助根因分析
- [ ] 多租户支持
- [ ] 更多 Exporter（MySQL、Redis、Nginx）
- [ ] Web 管理后台

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。

---

## 🙏 致谢

- [Prometheus](https://prometheus.io/) - 强大的监控系统
- [Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/) - 告警管理
- [python-telegram-bot](https://python-telegram-bot.org/) - Telegram Bot SDK
- [Grafana](https://grafana.com/) - 数据可视化平台

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！**

Made with ❤️ by [7Ese](https://github.com/7Ese)

</div>
