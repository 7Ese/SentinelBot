#!/bin/bash

# 自动获取当前脚本所在目录，解决服务器路径不一致问题
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
MONITORING_DIR="$PROJECT_DIR/monitoring"

# 自动探测 docker compose 命令
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif docker-compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ 错误: 未检测到 Docker Compose。"
    exit 1
fi

# 强力清理冲突进程逻辑 (防止 Token 被占用)
cleanup_conflicts() {
    echo "🧹 正在清理宿主机上的残留机器人进程..."
    # 杀掉所有运行 sentinel.py 的 python 进程
    ps aux | grep -Ei "sentinel.py" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
}

usage() {
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
}

if [ -z "$1" ]; then
    usage
fi

case "$1" in
    start)
        cleanup_conflicts
        echo "🚀 正在启动监控堆栈与 SentinelBot..."
        cd "$MONITORING_DIR" && $DOCKER_COMPOSE up -d --build
        ;;
    stop)
        echo "🛑 正在停止所有服务..."
        cd "$MONITORING_DIR" && $DOCKER_COMPOSE down
        cleanup_conflicts
        ;;
    restart)
        echo "🔄 正在重启所有服务..."
        cleanup_conflicts
        cd "$MONITORING_DIR" && $DOCKER_COMPOSE restart
        ;;
    status)
        echo "📊 当前服务运行状态："
        cd "$MONITORING_DIR" && $DOCKER_COMPOSE ps
        ;;
    logs)
        echo "📜 正在查看服务日志 (Ctrl+C 退出)..."
        cd "$MONITORING_DIR" && $DOCKER_COMPOSE logs -f
        ;;
    *)
        usage
        ;;
esac
