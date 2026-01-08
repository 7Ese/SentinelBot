# 🚀 部署指南

本文档提供详细的部署步骤和配置说明。

## 📋 目录

- [环境准备](#环境准备)
- [部署步骤](#部署步骤)
- [配置说明](#配置说明)
- [验证部署](#验证部署)
- [故障排查](#故障排查)

---

## 环境准备

### 1. 服务器要求

**监控服务器（运行 SentinelBot）**
- 系统：Linux (推荐 Ubuntu 20.04+)
- CPU：1 核及以上
- 内存：1GB 及以上
- 磁盘：10GB 及以上
- Docker：20.10+
- Docker Compose：2.0+

**被监控服务器**
- 需要安装 Node Exporter
- 开放 9100 端口（可配置防火墙白名单）

### 2. 准备 Telegram Bot

#### 创建 Bot
1. 在 Telegram 中搜索 `@BotFather`
2. 发送 `/newbot` 命令
3. 按提示设置 Bot 名称和用户名
4. 保存返回的 **Bot Token**

#### 获取 User ID
1. 搜索 `@userinfobot`
2. 向它发送任意消息
3. 记录你的 **User ID**

#### 创建告警群组
1. 创建一个新的 Telegram 群组
2. 将你的 Bot 加入群组
3. 向群组发送一条消息
4. 访问以下 URL（替换 YOUR_BOT_TOKEN）：
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
5. 在返回的 JSON 中找到 `chat.id`（负数）

---

## 部署步骤

### Step 1: 克隆项目

```bash
git clone https://github.com/7Ese/SentinelBot.git
cd SentinelBot
```

### Step 2: 配置环境变量

```bash
# 复制环境变量模板
cp .env.example monitoring/.env

# 编辑配置文件
vim monitoring/.env
```

填入你的配置：

```bash
# Telegram Bot Token（从 BotFather 获取）
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# 管理员 User ID（从 userinfobot 获取）
TELEGRAM_ADMIN_ID=123456789

# 告警推送的群组 ID（负数）
TELEGRAM_CHAT_ID=-1001234567890

# MFA 密钥（可选，如不需要可留空）
MFA_SECRET=

# AWS 配置（如需监控 RDS）
AWS_REGION=ap-east-1
AWS_ACCESS_KEY_ID=YOUR_AWS_ACCESS_KEY_ID_HERE
AWS_SECRET_ACCESS_KEY=YOUR_AWS_SECRET_ACCESS_KEY_HERE

# Grafana 管理员密码（建议修改）
GF_SECURITY_ADMIN_PASSWORD=your_secure_password
```

### Step 3: 配置监控目标

编辑 `monitoring/prometheus/prometheus.yml`：

```yaml
scrape_configs:
  - job_name: 'nodes'
    scrape_interval: 15s
    static_configs:
      # 项目 A
      - targets:
          - '10.0.1.10:9100'
        labels:
          project: 'ProjectA'
          role: 'web'
          alias: 'web-server-01'
      
      - targets:
          - '10.0.1.20:9100'
        labels:
          project: 'ProjectA'
          role: 'api'
          alias: 'api-server-01'
```

**标签说明**：
- `project`: 项目名称（用于分组）
- `role`: 服务器角色（web/api/database 等）
- `alias`: 显示别名（在 Bot 中显示）

### Step 4: 配置 RDS 监控（可选）

如果需要监控 AWS RDS：

1. 确保 AWS 凭证有 CloudWatch 读取权限
2. 编辑 `sentinel/sentinel.py`，添加 RDS 实例：

```python
RDS_INSTANCES: List[Dict[str, str]] = [
    {"id": "my-rds-instance", "project": "ProjectA", "alias": "生产数据库"},
]
```

### Step 5: 在被监控服务器上安装 Node Exporter

在每台需要监控的服务器上执行：

```bash
# 下载 Node Exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz
tar -xvf node_exporter-1.7.0.linux-amd64.tar.gz
sudo mv node_exporter-1.7.0.linux-amd64/node_exporter /usr/local/bin/

# 创建 Systemd 服务
sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<EOF
[Unit]
Description=Node Exporter
After=network.target

[Service]
Type=simple
User=nobody
ExecStart=/usr/local/bin/node_exporter
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable node_exporter
sudo systemctl start node_exporter

# 验证（应该能看到指标）
curl http://localhost:9100/metrics
```

### Step 6: 启动 SentinelBot

```bash
# 启动所有服务
./manage.sh start

# 查看服务状态
./manage.sh status

# 查看日志
./manage.sh logs
```

---

## 配置说明

### 告警规则配置

编辑 `monitoring/prometheus/rules/basic-alerts.yml`：

```yaml
groups:
  - name: custom-alerts
    rules:
      - alert: MyCustomAlert
        expr: your_metric > threshold
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "告警摘要"
          description: "{{ $labels.instance }} 详细描述"
```

### 告警路由配置

编辑 `monitoring/alertmanager/alertmanager.yml`：

```yaml
route:
  routes:
    - match:
        severity: "critical"
      repeat_interval: 30m
    
    - match:
        severity: "warning"
      repeat_interval: 2h
```

---

## 验证部署

### 1. 检查容器状态

```bash
cd monitoring
docker-compose ps
```

应该看到所有容器都在运行：
```
NAME                STATUS
prometheus          Up
alertmanager        Up
cloudwatch-exporter Up
mfa-bot             Up
grafana             Up
```

### 2. 测试 Web 界面

- Prometheus: http://localhost:9090
- Alertmanager: http://localhost:9093
- Grafana: http://localhost:3000

### 3. 测试 Telegram Bot

在 Telegram 中向你的 Bot 发送 `/start`，应该收到欢迎消息。

### 4. 测试告警

手动触发一个测试告警：

```bash
# 在 Prometheus 界面 (http://localhost:9090) 执行
# Alerts -> 查看是否有告警规则
# 或者停止一个 Node Exporter 触发 InstanceDown 告警
```

---

## 故障排查

### Bot 无响应

```bash
# 查看 Bot 日志
docker-compose logs sentinel-bot

# 常见问题：
# 1. TELEGRAM_BOT_TOKEN 配置错误
# 2. Bot 没有在群组中或没有发送消息权限
```

### Prometheus 无法采集数据

```bash
# 检查目标状态
http://localhost:9090/targets

# 常见问题：
# 1. 服务器防火墙未开放 9100 端口
# 2. prometheus.yml 中 IP 地址配置错误
# 3. Node Exporter 未启动

# 手动测试连接
curl http://your-server-ip:9100/metrics
```

### 告警未推送

```bash
# 检查 Alertmanager 状态
http://localhost:9093

# 查看 Webhook 日志
docker-compose logs sentinel-bot

# 常见问题：
# 1. TELEGRAM_CHAT_ID 配置错误
# 2. Alertmanager 路由配置问题
# 3. Bot 在群组中权限不足
```

### CloudWatch Exporter 报错

```bash
# 查看日志
docker-compose logs cloudwatch-exporter

# 常见问题：
# 1. AWS 凭证配置错误
# 2. IAM 权限不足（需要 cloudwatch:GetMetricStatistics）
# 3. 区域配置错误
```

---

## 安全建议

### 1. 环境变量保护

```bash
# 确保 .env 文件权限正确
chmod 600 monitoring/.env

# 不要将 .env 文件提交到 Git
# .gitignore 已包含该规则
```

### 2. 防火墙配置

```bash
# 监控服务器
# 仅允许被监控服务器访问 Prometheus
sudo ufw allow from 10.0.1.0/24 to any port 9090

# 被监控服务器
# 仅允许监控服务器访问 Node Exporter
sudo ufw allow from MONITOR_SERVER_IP to any port 9100
```

### 3. Grafana 密码

记得修改默认密码：
```bash
GF_SECURITY_ADMIN_PASSWORD=your_strong_password_here
```

---

## 升级指南

### 更新镜像

```bash
cd monitoring
docker-compose pull
./manage.sh restart
```

### 更新配置

```bash
# 修改配置后重启
./manage.sh restart
```

---

## 备份与恢复

### 备份配置

```bash
# 备份配置文件
tar -czf sentinelbot-backup-$(date +%Y%m%d).tar.gz \
  monitoring/prometheus/prometheus.yml \
  monitoring/prometheus/rules/ \
  monitoring/alertmanager/alertmanager.yml \
  monitoring/cloudwatch/rds-config.yml \
  monitoring/.env
```

### 恢复配置

```bash
# 解压备份
tar -xzf sentinelbot-backup-20260108.tar.gz

# 重启服务
./manage.sh restart
```

---

## 联系支持

如有问题，请：
1. 查看 [常见问题](README.md#常见问题)
2. 提交 [Issue](https://github.com/7Ese/SentinelBot/issues)
3. 查看项目文档

---

**祝部署顺利！** 🎉
