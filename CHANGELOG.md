# 📝 更新日志

## [1.0.0] - 2026-01-08

### 🎉 首次发布

#### ✨ 核心功能
- ✅ **Prometheus 监控集成**
  - 支持 Node Exporter 服务器监控
  - CPU、内存、磁盘、负载等全方位指标采集
  - 多分区磁盘监控
  
- ✅ **Alertmanager 智能告警**
  - 分级告警路由（Critical/Warning）
  - 宕机告警零延迟推送
  - 防刷屏机制（超过10条自动折叠）
  - 时间本地化（UTC → CST）

- ✅ **Telegram Bot 交互界面**
  - 实时服务器资源查询
  - 多项目分组浏览
  - 节点详细指标展示
  - 趋势分析（↗️ 上升 / ↘️ 下降 / ➡️ 平稳）
  - 异常节点筛选
  - 当前告警查看

- ✅ **AWS CloudWatch 集成**
  - RDS 数据库监控
  - CPU、连接数、磁盘、内存指标

- ✅ **MFA 验证码生成**
  - TOTP 验证码支持
  - 实时倒计时进度条
  - 权限控制

#### 🛠️ 技术特性
- Docker Compose 一键部署
- 自动化管理脚本（manage.sh）
- 完整的告警规则集（15+ 规则）
- 模块化设计，易于扩展

#### 📚 文档
- 详细的 README.md 项目说明
- DEPLOYMENT.md 部署指南
- CONTRIBUTING.md 贡献指南
- 完整的配置示例

#### 🔒 安全性
- 环境变量隔离
- .gitignore 配置完善
- 无硬编码敏感信息

---

## 项目命名历史

### 2026-01-08
- **重命名**：`SentineBot` → `SentinelBot`
- **目录重构**：`mfa/` → `sentinel/`
- **文件重命名**：`mfa.py` → `sentinel.py`
- **容器重命名**：`mfa-bot` → `sentinel-bot`
- **理由**：更准确反映项目功能，"Sentinel"（哨兵）更符合监控系统的定位

---

## 未来规划

### v1.1.0 (计划中)
- [ ] 支持服务发现（Consul / Kubernetes）
- [ ] 接入长期存储（Thanos / VictoriaMetrics）
- [ ] 更多 Exporter（MySQL、Redis、Nginx）
- [ ] Web 管理后台

### v1.2.0 (计划中)
- [ ] AI 辅助根因分析
- [ ] 多租户支持
- [ ] 自定义告警模板
- [ ] 移动端 Dashboard

---

## 贡献者

感谢所有为 SentinelBot 项目做出贡献的开发者！

---

**更新格式说明**：
- 🎉 重大更新
- ✨ 新功能
- 🐛 Bug 修复
- 📚 文档更新
- 🔒 安全更新
- ⚡ 性能优化
- 🔧 配置更新
