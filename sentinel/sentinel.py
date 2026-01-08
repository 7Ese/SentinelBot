#!/usr/bin/env python3

import logging
import os
import time
import threading
import json
import re
import datetime
from typing import Dict, List, Any, Optional

import pyotp
import requests
from flask import Flask, request
from werkzeug.serving import make_server
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ==========================================
# 🔧 配置区域
# ==========================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# 环境变量
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MFA_SECRET = os.getenv("MFA_SECRET")
ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
CLOUDWATCH_EXPORTER_URL = os.getenv("CLOUDWATCH_EXPORTER_URL", "http://cloudwatch-exporter:9106/metrics")

RDS_INSTANCES: List[Dict[str, str]] = [
      {"id": "project-a-db", "project": "ProjectA", "alias": "ProjectA 主库"},
      {"id": "project-b-db",  "project": "ProjectB", "alias": "ProjectB 主库"},
]

# ==========================================
# 🛡️ MFA 功能模块
# ==========================================

def get_totp_info():
    if not MFA_SECRET:
        return "❌ No Secret", 0
    totp = pyotp.TOTP(MFA_SECRET)
    code = totp.now()
    remaining_seconds = totp.interval - (time.time() % totp.interval)
    return code, int(remaining_seconds)

def mfa_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if str(user_id) != str(ADMIN_ID):
        update.message.reply_text("⛔️ Access Denied")
        return
    send_mfa_message(update.message.reply_text)

def send_mfa_message(send_func):
    code, remaining = get_totp_info()
    bar_length = 10
    filled = int((remaining / 30) * bar_length)
    bar = "▓" * filled + "░" * (bar_length - filled)
    
    message = (
        f"🔐 *SentinelBot MFA Verify*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Code: `{code}`\n"
        f"Time: {remaining}s {bar}\n"
        f"━━━━━━━━━━━━━━━━"
    )
    keyboard = [
        [InlineKeyboardButton("🔄 刷新 / Refresh", callback_data='refresh_code')],
        [InlineKeyboardButton("🏠 返回主菜单", callback_data='main_menu')]
    ]
    send_func(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

# ==========================================
# 📊 监控核心逻辑 (100% 还原旧版)
# ==========================================

def prom_query(expr: str) -> Dict[str, Any]:
    url = PROMETHEUS_URL.rstrip("/") + "/api/v1/query"
    try:
        resp = requests.get(url, params={"query": expr}, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Prometheus Query Failed: {e}")
        return {}

def query_single_value(expr: str) -> Optional[float]:
    data = prom_query(expr)
    result = data.get("data", {}).get("result", [])
    if not result: return None
    try:
        return float(result[0].get("value", [None, None])[1])
    except:
        return None

def get_nodes_grouped_by_project() -> Dict[str, List[Dict[str, str]]]:
    data = prom_query('up{job="nodes"}')
    result = data.get("data", {}).get("result", [])
    projects: Dict[str, List[Dict[str, str]]] = {}

    for item in result:
        metric = item.get("metric", {})
        project = metric.get("project", "unknown")
        instance = metric.get("instance", "")
        alias = metric.get("alias", instance)
        role = metric.get("role", "unknown")

        if project not in projects:
            projects[project] = []
        projects[project].append({
            "instance": instance,
            "alias": alias,
            "role": role,
        })

    for proj in projects:
        projects[proj].sort(key=lambda x: x["alias"])
    return projects

def get_rds_grouped_by_project() -> Dict[str, List[Dict[str, Any]]]:
    if not RDS_INSTANCES: return {}
    try:
        resp = requests.get(CLOUDWATCH_EXPORTER_URL, timeout=5)
        resp.raise_for_status()
        text = resp.text
    except Exception as e:
        logger.warning(f"Exporter fetch failed: {e}")
        return {}

    id_to_project = {item["id"]: item.get("project", "unknown") for item in RDS_INSTANCES}
    id_to_alias = {item["id"]: item.get("alias", item["id"]) for item in RDS_INSTANCES}
    
    metric_map = {
        "aws_rds_cpuutilization_average": "cpu",
        "aws_rds_database_connections_average": "conns",
        "aws_rds_freeable_memory_average": "free_mem",
        "aws_rds_free_storage_space_average": "free_storage",
    }
    
    inst_stats = {}
    line_re = re.compile(r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\{(?P<labels>[^}]*)\}\s+(?P<value>[-0-9.eE]+)")
    
    for line in text.splitlines():
        if not line or line.startswith("#"): continue
        m2 = line_re.match(line)
        if not m2: continue
        name = m2.group("name")
        if name not in metric_map: continue
        
        labels_str = m2.group("labels")
        value_str = m2.group("value")
        labels = {}
        for part in labels_str.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k.strip()] = v.strip().strip('"')
        
        inst = labels.get("dbinstance_identifier") or labels.get("DBInstanceIdentifier")
        if not inst: continue
        try:
            val = float(value_str)
            inst_stats.setdefault(inst, {})[metric_map[name]] = val
        except: continue

    projects = {}
    for inst, stats in inst_stats.items():
        if inst not in id_to_project: continue
        project = id_to_project[inst]
        item = {
            "id": inst,
            "alias": id_to_alias.get(inst, inst),
            "cpu": stats.get("cpu"),
            "conns": stats.get("conns"),
            "free_mem": stats.get("free_mem"),
            "free_storage": stats.get("free_storage"),
        }
        projects.setdefault(project, []).append(item)
    
    for proj in projects:
        projects[proj].sort(key=lambda x: x["alias"])
    return projects

def get_node_labels(instance: str) -> Dict[str, str]:
    data = prom_query(f'up{{job="nodes",instance="{instance}"}}')
    result = data.get("data", {}).get("result", [])
    if not result:
        return {"instance": instance, "alias": instance, "role": "unknown", "project": "unknown"}
    metric = result[0].get("metric", {})
    return {
        "instance": metric.get("instance", instance),
        "alias": metric.get("alias", instance),
        "role": metric.get("role", "unknown"),
        "project": metric.get("project", "unknown"),
    }

def get_node_status(instance: str) -> Dict[str, Optional[float]]:
    # CPU
    cpu_expr = f'avg(1 - rate(node_cpu_seconds_total{{instance="{instance}",mode="idle"}}[5m])) * 100'
    cpu_percent = query_single_value(cpu_expr)

    # Load1
    load1 = query_single_value(f'node_load1{{instance="{instance}"}}')

    # Mem
    mem_total = query_single_value(f'node_memory_MemTotal_bytes{{instance="{instance}"}}')
    mem_avail = query_single_value(f'node_memory_MemAvailable_bytes{{instance="{instance}"}}')
    mem_percent = None
    mem_used_gib = None
    mem_total_gib = None
    if mem_total and mem_avail and mem_total > 0:
        mem_used = mem_total - mem_avail
        mem_percent = (mem_used / mem_total) * 100.0
        mem_used_gib = mem_used / (1024**3)
        mem_total_gib = mem_total / (1024**3)

    # Disk summary:
    # - disk_percent: worst partition usage across all meaningful mountpoints (/, /data, etc.)
    # - disk_root_*: root partition (/) usage, used for node detail display
    fs_filter = 'fstype!~"tmpfs|overlay|squashfs"'
    mp_filter = 'mountpoint!~"^/(proc|sys|run)($|/)"'

    # Worst disk usage %
    worst_expr = (
        f'max(((node_filesystem_size_bytes{{instance="{instance}",{fs_filter},{mp_filter}}} '
        f'- node_filesystem_avail_bytes{{instance="{instance}",{fs_filter},{mp_filter}}}) '
        f'/ node_filesystem_size_bytes{{instance="{instance}",{fs_filter},{mp_filter}}}) * 100)'
    )
    disk_percent = query_single_value(worst_expr)

    # Root (/) usage for detail view
    disk_root_total = query_single_value(
        f'node_filesystem_size_bytes{{instance="{instance}",mountpoint="/",{fs_filter}}}'
    )
    disk_root_avail = query_single_value(
        f'node_filesystem_avail_bytes{{instance="{instance}",mountpoint="/",{fs_filter}}}'
    )
    disk_root_percent = None
    disk_root_used_gib = None
    disk_root_total_gib = None
    if disk_root_total and disk_root_avail is not None and disk_root_total > 0:
        disk_root_used = disk_root_total - disk_root_avail
        disk_root_percent = (disk_root_used / disk_root_total) * 100.0
        disk_root_used_gib = disk_root_used / (1024**3)
        disk_root_total_gib = disk_root_total / (1024**3)

    return {
        "cpu_percent": cpu_percent,
        "load1": load1,
        "mem_percent": mem_percent,
        "mem_used_gib": mem_used_gib,
        "mem_total_gib": mem_total_gib,
        # worst partition usage
        "disk_percent": disk_percent,
        # root partition usage (for node detail page)
        "disk_root_percent": disk_root_percent,
        "disk_root_used_gib": disk_root_used_gib,
        "disk_root_total_gib": disk_root_total_gib,
    }


def get_node_disks(instance: str) -> List[Dict[str, Any]]:
    """返回该节点所有有意义的磁盘分区使用情况（mountpoint 维度）。"""
    fs_filter = 'fstype!~"tmpfs|overlay|squashfs"'
    mp_filter = 'mountpoint!~"^/(proc|sys|run)($|/)"'

    # 先拿到所有 mountpoint（通过 size 指标的 label 集合）
    data = prom_query(
        f'node_filesystem_size_bytes{{instance="{instance}",{fs_filter},{mp_filter}}}'
    )
    result = data.get("data", {}).get("result", []) if data else []
    if not result:
        return []

    disks: List[Dict[str, Any]] = []
    for item in result:
        metric = item.get("metric", {}) or {}
        mountpoint = metric.get("mountpoint")
        device = metric.get("device")
        fstype = metric.get("fstype")

        if not mountpoint:
            continue

        size = query_single_value(
            f'node_filesystem_size_bytes{{instance="{instance}",mountpoint="{mountpoint}",{fs_filter}}}'
        )
        avail = query_single_value(
            f'node_filesystem_avail_bytes{{instance="{instance}",mountpoint="{mountpoint}",{fs_filter}}}'
        )
        ro = query_single_value(
            f'node_filesystem_readonly{{instance="{instance}",mountpoint="{mountpoint}",{fs_filter}}}'
        )

        # 跳过只读分区（例如某些系统挂载）
        if ro is not None and ro != 0:
            continue

        if size is None or avail is None or size <= 0:
            continue

        used = size - avail
        used_pct = used / size * 100.0

        disks.append({
            "mountpoint": mountpoint,
            "device": device,
            "fstype": fstype,
            "used_pct": used_pct,
            "used_gib": used / (1024**3),
            "total_gib": size / (1024**3),
        })

    # 排序：/ 最前，其它按字母
    disks.sort(key=lambda x: (0 if x["mountpoint"] == "/" else 1, x["mountpoint"]))
    return disks

# 格式化工具
def fmt_pct(v): return "—" if v is None else "%.1f%%" % v
def fmt_load(v): return "—" if v is None else "%.2f" % v
def fmt_gib_pair(used, total):
    if used is None or total is None: return "—"
    return "%.1fG / %.1fG" % (used, total)

def level_emoji(v):
    if v is None: return "⚪"
    if v >= 90: return "🔴"
    if v >= 80: return "🟠"
    if v >= 60: return "🟡"
    return "🟢"

def overall_emoji(cpu, mem, disk):
    vals = [x for x in [cpu, mem, disk] if x is not None]
    if not vals: return "⚪"
    return level_emoji(max(vals))

def get_metric_trend(expr_current: str, threshold: float = 0.1) -> str:
    """
    计算指标趋势
    :param expr_current: 当前值的 PromQL 表达式
    :param threshold: 变化阈值（默认 10%）
    :return: 趋势箭头 ↗️/↘️/➡️
    """
    current = query_single_value(expr_current)
    if current is None:
        return ""
    
    # 查询 5 分钟前的值
    expr_past = f"{expr_current} offset 5m"
    past = query_single_value(expr_past)
    
    if past is None or past == 0:
        return ""
    
    change_rate = (current - past) / past
    
    if change_rate > threshold:
        return "↗️"
    elif change_rate < -threshold:
        return "↘️"
    else:
        return "➡️"

def is_node_abnormal(status: Dict[str, Optional[float]]) -> bool:
    """
    判断节点是否异常
    :param status: 节点状态字典
    :return: True 表示异常
    """
    cpu = status.get("cpu_percent")
    mem = status.get("mem_percent")
    disk = status.get("disk_percent")
    
    if cpu and cpu > 80:
        return True
    if mem and mem > 85:
        return True
    if disk and disk > 85:
        return True
    
    return False

# ==========================================
# 📺 菜单与回调逻辑 (完全还原)
# ==========================================

def start_command(update: Update, context: CallbackContext):
    show_main_menu(update, True)

def show_main_menu(update, is_new_message=False):
    keyboard = [
        [InlineKeyboardButton("🔐 MFA 验证码", callback_data="show_mfa")],
        [InlineKeyboardButton("📂 浏览项目服务器", callback_data="main:projects")],
        [InlineKeyboardButton("📊 查看项目汇总", callback_data="main:status")],
        [InlineKeyboardButton("🚨 当前告警", callback_data="alerts_menu")],
        [InlineKeyboardButton("❌ 关闭", callback_data="cancel")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    text = (
        "👋 若 *SentinelBot* 已连接。\n\n"
        "你可以：\n"
        "• 获取 MFA 验证码\n"
        "• 浏览服务器资源\n"
        "• 查看项目健康状态\n\n"
        "🏠 *主菜单*"
    )
    if is_new_message:
        update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    
    try:
        # MFA 相关
        if data == "show_mfa":
            send_mfa_message(query.edit_message_text)
        elif data == "refresh_code":
            try:
                code, remaining = get_totp_info()
                bar_length = 10
                filled = int((remaining / 30) * bar_length)
                bar = "▓" * filled + "░" * (bar_length - filled)
                new_text = f"🔐 *SentinelBot MFA Verify*\n━━━━━━━━━━━━━━━━\nCode: `{code}`\nTime: {remaining}s {bar}\n━━━━━━━━━━━━━━━━"
                query.edit_message_text(text=new_text, reply_markup=query.message.reply_markup, parse_mode=ParseMode.MARKDOWN)
            except: pass
            
        # 核心导航
        elif data == "main_menu":
            show_main_menu(update)
        elif data == "cancel":
            query.edit_message_text("操作已取消。\n发送 /start 重新开始。")
            
        # 项目浏览
        elif data == "main:projects":
            show_nodes_project_selector(query)
        elif data.startswith("project:"):
            project = data.split(":", 1)[1]
            handle_project(query, project)
        elif data.startswith("nodes_of_project:"):
            project = data.split(":", 1)[1]
            handle_project(query, project)
        elif data.startswith("node:"):
            instance = data.split(":", 1)[1]
            handle_node(query, instance)
        elif data.startswith("rds:"):
            parts = data.split(":", 2)
            handle_rds_detail(query, parts[1], parts[2])
            
        # 状态汇总
        elif data == "main:status":
            show_status_project_selector(query)
        elif data.startswith("status_project:"):
            parts = data.split(":", 2)
            project = parts[1]
            filter_mode = parts[2] if len(parts) > 2 else "all"
            handle_status_project(query, project, filter_mode)
            
        # 告警
        elif data == "alerts_menu":
            show_current_alerts(query)
            
        query.answer()
    except Exception as e:
        logger.error(f"Callback error: {e}")
        query.answer("Error processing request")

def show_nodes_project_selector(query):
    node_projects = get_nodes_grouped_by_project()
    rds_projects = get_rds_grouped_by_project()
    all_projects = sorted(set(node_projects.keys()) | set(rds_projects.keys()))
    
    if not all_projects:
        query.edit_message_text("⚠️ 无被监控项目。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 返回", callback_data="main_menu")]]))
        return
        
    keyboard = []
    for proj in all_projects:
        keyboard.append([InlineKeyboardButton(f"📂 {proj}", callback_data=f"project:{proj}")])
    keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
    query.edit_message_text("选择项目进行浏览：", reply_markup=InlineKeyboardMarkup(keyboard))

def show_status_project_selector(query):
    node_projects = get_nodes_grouped_by_project()
    rds_projects = get_rds_grouped_by_project()
    all_projects = sorted(set(node_projects.keys()) | set(rds_projects.keys()))
    
    keyboard = []
    for proj in all_projects:
        keyboard.append([InlineKeyboardButton(f"📊 {proj}", callback_data=f"status_project:{proj}")])
    keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
    query.edit_message_text("选择项目（查看汇总）：", reply_markup=InlineKeyboardMarkup(keyboard))

def handle_project(query, project):
    node_projects = get_nodes_grouped_by_project()
    rds_projects = get_rds_grouped_by_project()
    
    nodes = node_projects.get(project, [])
    rds_list = rds_projects.get(project, [])
    
    lines = [
        f"📂 *项目 {project} 资源概览*",
        ""
    ]
    
    if nodes:
        lines.append(f"🖥 *服务器节点* ({len(nodes)} 台)")
        lines.append("")
        for node in nodes:
            status = get_node_status(node["instance"])
            cpu_val = status["cpu_percent"]
            mem_pct = status.get("mem_percent")
            disk_pct = status.get("disk_percent")
            
            icon = level_emoji(max(filter(None, [cpu_val, mem_pct, disk_pct])))
            ip = node["instance"].split(":")[0]
            
            # 优化：别名 (IP) 格式
            lines.append(f"{icon} *{node['alias']}* (`{ip}`)") 
            lines.append(f"   CPU {fmt_pct(cpu_val)} ｜ MEM {fmt_pct(mem_pct)} ｜ DISK {fmt_pct(disk_pct)}")
            lines.append("")
    else:
        lines.append("🖥 *服务器节点*: _无_")
        lines.append("")
    
    if rds_list:
        lines.append(f"🗄 *RDS 数据库* ({len(rds_list)} 个)")
        lines.append("")
        for r in rds_list:
            icon = level_emoji(r['cpu'])
            free_st_gib = r.get('free_storage') / (1024**3) if r.get('free_storage') else None
            
            lines.append(f"{icon} *{r['alias']}* (`{r['id']}`)") 
            lines.append(f"   CPU {fmt_pct(r['cpu'])} ｜ 连接 {int(r['conns'] or 0)} ｜ 磁盘余额 {('%.1fG' % free_st_gib) if free_st_gib else '—'}")
            lines.append("")
    else:
         lines.append("🗄 *RDS 数据库*: _无_")
         
    keyboard = []
    for node in nodes:
        ip = node["instance"].split(":")[0]
        btn_text = f"{node['alias']} ({node['role']})\n{ip}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"node:{node['instance']}")])
        
    for r in rds_list:
        keyboard.append([InlineKeyboardButton(f"🗄 {r['alias']}", callback_data=f"rds:{project}:{r['id']}")])
        
    keyboard.append([InlineKeyboardButton("⬅ 返回项目列表", callback_data="main:projects")])
    keyboard.append([InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")])
    
    query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

def handle_node(query, instance):
    labels = get_node_labels(instance)
    st = get_node_status(instance)
    ip = labels["instance"].split(":")[0]

    # 计算趋势（根分区 /）
    cpu_expr = f'avg(1 - rate(node_cpu_seconds_total{{instance="{instance}",mode="idle"}}[5m])) * 100'
    cpu_trend = get_metric_trend(cpu_expr)

    mem_expr = (
        f'(node_memory_MemTotal_bytes{{instance="{instance}"}} - node_memory_MemAvailable_bytes{{instance="{instance}"}}) '
        f'/ node_memory_MemTotal_bytes{{instance="{instance}"}} * 100'
    )
    mem_trend = get_metric_trend(mem_expr)

    disk_expr = (
        f'(node_filesystem_size_bytes{{instance="{instance}",mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}} '
        f'- node_filesystem_avail_bytes{{instance="{instance}",mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}}) '
        f'/ node_filesystem_size_bytes{{instance="{instance}",mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}} * 100'
    )
    disk_trend = get_metric_trend(disk_expr)

    cpu_emo = level_emoji(st.get("cpu_percent"))
    mem_emo = level_emoji(st.get("mem_percent"))
    disk_root_emo = level_emoji(st.get("disk_root_percent"))
    worst_disk_emo = level_emoji(st.get("disk_percent"))

    # 磁盘分区列表（包含 /data 等）
    disks = get_node_disks(instance)
    disk_lines: List[str] = []
    if disks:
        disk_lines.append("🟢 *磁盘分区*：")
        for d in disks:
            emo = level_emoji(d.get("used_pct"))
            mp = d.get("mountpoint", "?")
            disk_lines.append(
                f"{emo} `{mp}`：{d['used_pct']:.1f}%  ({d['used_gib']:.1f}G / {d['total_gib']:.1f}G)"
            )
    else:
        disk_lines.append("💽 *磁盘分区*：—")

    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🖥 *服务器详情*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"项目：*{labels['project']}*\n"
        f"别名：`{labels['alias']}`\n"
        f"角色：`{labels['role']}`\n"
        f"IP：`{ip}`\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{cpu_emo} *CPU*：{fmt_pct(st.get('cpu_percent'))} {cpu_trend}  (load1: {fmt_load(st.get('load1'))})\n"
        f"{mem_emo} *内存*：{fmt_pct(st.get('mem_percent'))} {mem_trend}\n"
        f"{mem_emo} 容量：{fmt_gib_pair(st.get('mem_used_gib'), st.get('mem_total_gib'))}\n"
        f"{disk_root_emo} *根分区* (/)：{fmt_pct(st.get('disk_root_percent'))} {disk_trend}\n"
        f"{disk_root_emo} 容量：{fmt_gib_pair(st.get('disk_root_used_gib'), st.get('disk_root_total_gib'))}\n"
        f"{worst_disk_emo} *最紧张分区*：{fmt_pct(st.get('disk_percent'))}\n"
        + ("\n".join(disk_lines) + "\n")
        + "━━━━━━━━━━━━━━━━━━━━"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 刷新", callback_data=f"node:{instance}")],
        [InlineKeyboardButton("⬅ 返回项目", callback_data=f"nodes_of_project:{labels['project']}")],
        [InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]
    ]
    query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

def handle_rds_detail(query, project, rds_id):
    rds_projects = get_rds_grouped_by_project()
    rds_list = rds_projects.get(project, [])
    item = next((r for r in rds_list if r["id"] == rds_id), None)
    
    if not item:
        query.edit_message_text("❌ RDS 实例未找到", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 返回", callback_data="main_menu")]]))
        return
        
    cpu = item.get("cpu")
    conns = item.get("conns")
    free_mem_gib = item.get("free_mem") / (1024**3) if item.get("free_mem") else None
    free_st_gib = item.get("free_storage") / (1024**3) if item.get("free_storage") else None
    
    cpu_emo = level_emoji(cpu)
    
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "🗄 *RDS 实例详情*",
        "━━━━━━━━━━━━━━━━━━━━",
        f"项目：*{project}*",
        f"实例 ID：`{item['id']}`",
        f"别名：`{item['alias']}`",
        "",
        "📊 *资源使用*",
        f"{cpu_emo} CPU：{fmt_pct(cpu)}",
        f"🔗 连接数：{int(conns or 0)}",
        f"💾 可用磁盘：{'%.1f GB' % free_st_gib if free_st_gib else '—'}",
        f"🧠 可用内存：{'%.1f GB' % free_mem_gib if free_mem_gib else '—'}",
        "━━━━━━━━━━━━━━━━━━━━"
    ]
    
    keyboard = [
        [InlineKeyboardButton("🔄 刷新", callback_data=f"rds:{project}:{rds_id}")],
        [InlineKeyboardButton("⬅ 返回项目", callback_data=f"project:{project}")],
        [InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]
    ]
    query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

def handle_status_project(query, project, filter_mode="all"):
    node_projects = get_nodes_grouped_by_project()
    nodes = node_projects.get(project, [])
    rds_projects = get_rds_grouped_by_project()
    rds_list = rds_projects.get(project, [])
    
    lines = [
        f"📊 *项目 {project} 当前资源概览*",
        "_(CPU / 内存 / 磁盘 为当前瞬时状态，仅用于快速体感)_",
        ""
    ]
    
    # 过滤提示
    if filter_mode == "alert":
        lines.append("⚠️ *仅显示异常节点*")
        lines.append("")
    
    if nodes:
        lines.append("🌐 *服务器节点*")
        lines.append("")
        
        displayed_count = 0
        for node in nodes:
            instance = node["instance"]
            st = get_node_status(instance)
            
            # 过滤逻辑
            if filter_mode == "alert" and not is_node_abnormal(st):
                continue
            
            displayed_count += 1
            
            # 计算趋势
            cpu_expr = f'avg(1 - rate(node_cpu_seconds_total{{instance="{instance}",mode="idle"}}[5m])) * 100'
            cpu_trend = get_metric_trend(cpu_expr)
            
            overall = overall_emoji(st["cpu_percent"], st["mem_percent"], st["disk_percent"])
            ip = instance.split(":")[0]
            
            lines.append(f"{overall} *{node['alias']}* (`{ip}`)") 
            lines.append(f"   CPU {fmt_pct(st['cpu_percent'])} {cpu_trend} ｜ MEM {fmt_pct(st['mem_percent'])} ｜ DISK {fmt_pct(st['disk_percent'])}")
            lines.append("")
        
        if filter_mode == "alert" and displayed_count == 0:
            lines.append("✅ _无异常节点_")
            lines.append("")
    else:
        lines.append("🌐 *服务器节点*: _无_")
        lines.append("")
        
    if rds_list:
        lines.append("🗄 *RDS 数据库*")
        lines.append("")
        
        displayed_rds_count = 0
        for r in rds_list:
            cpu = r.get("cpu")
            
            # RDS 过滤逻辑（仅判断 CPU）
            if filter_mode == "alert" and (cpu is None or cpu <= 80):
                continue
            
            displayed_rds_count += 1
            conns = r.get("conns")
            free_st_gib = r.get("free_storage") / (1024**3) if r.get("free_storage") else None
            free_mem_gib = r.get("free_mem") / (1024**3) if r.get("free_mem") else None
            
            emo = "🟢"
            if cpu and cpu > 80: emo = "🟠"
            if free_st_gib and free_st_gib < 20: emo = "🟠"
            
            lines.append(f"{emo} *{r['alias']}* (`{r['id']}`)")
            lines.append(f"   CPU {fmt_pct(cpu)} ｜ 连接 {int(conns or 0)} ｜ 磁盘 {('%.1fG' % free_st_gib) if free_st_gib else '—'} ｜ 内存 {('%.1fG' % free_mem_gib) if free_mem_gib else '—'}")
            lines.append("")
        
        if filter_mode == "alert" and displayed_rds_count == 0 and displayed_count == 0:
            # 如果节点和 RDS 都没有异常
            pass
    else:
        lines.append("🗄 *RDS 数据库*: _无_")
        
    # 按钮布局：三行
    keyboard = [
        [
            InlineKeyboardButton("📊 全部资源", callback_data=f"status_project:{project}:all"),
            InlineKeyboardButton("⚠️ 仅异常", callback_data=f"status_project:{project}:alert")
        ],
        [
            InlineKeyboardButton("🔄 刷新", callback_data=f"status_project:{project}:{filter_mode}"),
            InlineKeyboardButton("📂 查看服务器", callback_data=f"project:{project}")
        ],
        [
            InlineKeyboardButton("⬅ 返回项目选择", callback_data="main:status"),
            InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")
        ]
    ]
    query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

def show_current_alerts(query):
    url = PROMETHEUS_URL.rstrip("/") + "/api/v1/alerts"
    try:
        resp = requests.get(url, timeout=3)
        data = resp.json()
        alerts = data.get("data", {}).get("alerts", [])
        firing = [a for a in alerts if a.get("state") == "firing"]
        
        if not firing:
            query.edit_message_text("✅ 当前无 Firing 告警。", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 返回", callback_data="main_menu")]]))
            return
            
        # Group by project
        grouped = {}
        for a in firing:
            proj = a.get("labels", {}).get("project", "未分组")
            grouped.setdefault(proj, []).append(a)
            
        lines = ["🚨 *当前告警一览*"]
        for proj, items in grouped.items():
            lines.append(f"\n*项目 {proj}*:")
            for item in items:
                labels = item.get("labels", {})
                sev = labels.get("severity", "info")
                name = labels.get("alertname", "Alert")
                desc = item.get("annotations", {}).get("description", "")
                
                icon = "❌" if sev == "critical" else "⚠️" 
                lines.append(f"{icon} {name} ({sev})")
                if desc: lines.append(f"   _{desc}_")
                
        keyboard = [
            [InlineKeyboardButton("🔄 刷新", callback_data="alerts_menu")],
            [InlineKeyboardButton("🏠 主菜单", callback_data="main_menu")]
        ]
        query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        query.edit_message_text(f"❌ Error: {str(e)}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 返回", callback_data="main_menu")]]))

# ==========================================
# 🚒 Webhook & Scheduler (维持不变)
# ==========================================

app = Flask(__name__)
bot_instance = None

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        if data and 'alerts' in data:
            process_alerts(data)
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return "Error", 500

def process_alerts(data):
    if not bot_instance or not CHAT_ID: return
    alerts = data.get('alerts', [])
    firing = [a for a in alerts if a.get('status') == 'firing']
    resolved = [a for a in alerts if a.get('status') == 'resolved']
    
    if firing:
        msg, keyboard = format_alert_message(firing, "🔥 Firing")
        bot_instance.send_message(
            chat_id=CHAT_ID, 
            text=msg, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    if resolved:
        msg, keyboard = format_alert_message(resolved, "✅ Resolved")
        bot_instance.send_message(
            chat_id=CHAT_ID, 
            text=msg, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def format_alert_message(alerts_list, title):
    # 标题映射
    title_map = {
        "firing": "🔥 系统告警",
        "resolved": "✅ 告警恢复"
    }
    
    # 状态映射
    status_map = {
        "firing": "❌ Firing",
        "resolved": "✅ Resolved"
    }

    raw_title = title.lower().replace("🔥 ", "").replace("✅ ", "")
    display_title = title_map.get(raw_title, title)
    display_status = status_map.get(raw_title, raw_title)
    
    # 🛡️ 保护机制：防止告警风暴导致消息过长发送失败
    # 如果超过 10 条，只显示前 10 条，并在最后提示
    MAX_ALERTS = 10
    total_count = len(alerts_list)
    display_list = alerts_list[:MAX_ALERTS]
    
    lines = []
    
    for alert in display_list:
        labels = alert.get('labels', {})
        annotations = alert.get('annotations', {})
        
        # 提取关键字段
        project = labels.get('project', 'Unknown')
        alert_type = labels.get('alertname', 'Unknown')
        severity = labels.get('severity', 'info')
        
        # 兼容 RDS 和 Node 的实例标识
        instance = labels.get('instance') or labels.get('dbinstance_identifier') or 'Unknown'
        
        # 尝试提取角色
        role = labels.get('role', 'unknown')
        
        # 处理 IP：如果是 IP:Port 格式，取 IP；如果是 RDS ID，保持原样
        ip = instance.split(':')[0] if ':' in instance else instance
        
        # ⏰ 时间优化：UTC -> 北京时间 (UTC+8)
        starts_at_str = alert.get('startsAt')
        time_display = "Unknown"
        if starts_at_str:
            try:
                # 解析 ISO8601 (例如 2023-12-13T02:54:52.04Z)
                # 注意：简单的 string split 不够严谨，这里手动处理时区
                # 简单起见，假设输入是 UTC，手动 +8 小时
                if '.' in starts_at_str:
                    dt_str = starts_at_str.split('.')[0] # 去掉毫秒
                else:
                    dt_str = starts_at_str.replace('Z', '')
                    
                dt_struct = time.strptime(dt_str, '%Y-%m-%dT%H:%M:%S')
                ts = time.mktime(dt_struct)
                ts_cst = ts + 8 * 3600 # +8 hours
                time_struct_cst = time.gmtime(ts_cst) # gmtime 因为我们已经手动加了 offset
                time_display = time.strftime('%Y-%m-%d %H:%M:%S', time_struct_cst) + " CST"
            except Exception:
                time_display = starts_at_str # 解析失败回退到原始字符串

        desc = annotations.get('description') or annotations.get('summary') or '暂无说明'
        
        # 构建消息头
        lines.append(f"{display_title} ({project})")
        lines.append("")
        
        # 结构化字段
        # 优先显示 alias，没有则显示 instance
        display_name = labels.get('alias', instance)
        
        lines.append(f"🖥 *服务器*： `{display_name}`")
        lines.append(f"🏷 *角色*： `{role}`")
        lines.append(f"🌐 *IP*： `{ip}`")
        lines.append(f"📊 *告警类型*： `{alert_type}`")
        lines.append(f"📌 *状态*： *{display_status}* ({severity})")
        lines.append(f"⏰ *时间*： `{time_display}`")
        lines.append("")
        lines.append(f"📍 *说明*：")
        lines.append("")
        lines.append(desc)
        lines.append("━━━━━━━━━━━━━━━━")
        
    if total_count > MAX_ALERTS:
        lines.append(f"⚠️ *还有 {total_count - MAX_ALERTS} 条告警被折叠...*")

    # 新增：提取第一个告警的 instance 用于快捷操作
    first_alert = display_list[0] if display_list else None
    keyboard = []
    
    if first_alert:
        labels = first_alert.get('labels', {})
        instance = labels.get('instance')
        project = labels.get('project', 'unknown')
        
        if instance:
            keyboard.append([
                InlineKeyboardButton("🔍 查看节点详情", callback_data=f"node:{instance}")
            ])
        keyboard.append([
            InlineKeyboardButton("📊 查看项目汇总", callback_data=f"status_project:{project}:all")
        ])
    
    keyboard.append([InlineKeyboardButton("🏠 返回主菜单", callback_data="main_menu")])
    
    return "\n".join(lines), keyboard

def run_flask():
    make_server('0.0.0.0', 5000, app).serve_forever()

def daily_report_job(context: CallbackContext):
    if not CHAT_ID: return
    node_projects = get_nodes_grouped_by_project()
    total = sum(len(v) for v in node_projects.values())
    context.bot.send_message(chat_id=CHAT_ID, text=f"📋 *每日晨报*\n时间: {time.strftime('%H:%M')}\n监控节点: {total}\n✅ 系统正常", parse_mode=ParseMode.MARKDOWN)

# ==========================================
# 🚀 启动
# ==========================================

if __name__ == '__main__':
    if not BOT_TOKEN: exit(1)
    
    threading.Thread(target=run_flask, daemon=True).start()
    
    updater = Updater(BOT_TOKEN)
    dp = updater.dispatcher
    bot_instance = updater.bot
    
    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("mfa", mfa_command)) # 别名 mfa
    dp.add_handler(CommandHandler("FA", mfa_command))
    dp.add_handler(CallbackQueryHandler(handle_callback))
    
    # 已关闭每日晨报（按你的要求）
    # updater.job_queue.run_daily(daily_report_job, time=datetime.time(hour=0, minute=0, second=0))
    
    logger.info("Bot Started.")
    updater.start_polling()
    updater.idle()

