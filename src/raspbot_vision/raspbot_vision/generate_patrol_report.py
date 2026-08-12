#!/usr/bin/env python3
"""Generate a daily patrol report in Markdown from SQLite data.

Usage:
  python3 -m raspbot_vision.generate_patrol_report                # today
  python3 -m raspbot_vision.generate_patrol_report --days 7       # last 7 days
  python3 -m raspbot_vision.generate_patrol_report --date 2026-07-03
  python3 -m raspbot_vision.generate_patrol_report --output report.md
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Template

from .workspace import resolve_workspace_path, workspace_path

DEFAULT_DB = str(workspace_path('data', 'patrol', 'patrol_events.db'))

REPORT_TEMPLATE = Template("""\
# 巡检日报 — {{ date_str }}

> 生成时间：{{ generated_at }}
> 设备：Raspbot 巡检机器人 (Raspberry Pi 4B)

---

## 📊 总览

| 指标 | 数值 |
|------|------|
| 巡检总轮数 | {{ stats.total_rounds }} |
| 确认有人 | {{ stats.occupied_count }} |
| 确认无人 | {{ stats.empty_count }} |
| 不确定 | {{ stats.uncertain_count }} |
| 总观测次数 | {{ stats.total_observations }} |
| 最大同时人数 | {{ stats.max_person_count }} |
| 平均置信度 | {{ "%.2f"|format(stats.avg_confidence) if stats.avg_confidence else 'N/A' }} |

{% if stats.occupied_count > 0 %}
---

## 🚨 人员检测记录

| 时间 | 人数 | 置信度 | 检测角度 | 后端 |
|------|------|--------|----------|------|
{% for r in occupied_records -%}
| {{ r.finished_at }} | {{ r.max_person_count }} | {{ "%.2f"|format(r.max_confidence) }} | {{ r.occupied_positions }} | {{ r.detector_backend }} |
{% endfor %}
{% endif %}

---

## 📋 全部巡检记录

| # | 时间 | 判定 | 人数 | 置信度 |
|---|------|------|------|--------|
{% for r in all_records -%}
| {{ loop.index }} | {{ r.finished_at }} | {{ r.final_decision }} | {{ r.max_person_count }} | {{ "%.2f"|format(r.max_confidence) }} |
{% endfor %}

{% if not all_records %}
*今日暂无巡检记录*
{% endif %}

---

## 🔧 系统信息

| 项目 | 值 |
|------|-----|
| 数据库路径 | {{ db_path }} |
| 计日期范围 | {{ date_range }} |
| 检测后端 | {{ backends | join(', ') or 'N/A' }} |

{% if errors %}
---

## ⚠️ 异常记录

{% for e in errors %}
- {{ e.finished_at }}：**{{ e.error_msg }}**（后端 {{ e.detector_backend }}）
{% endfor %}
{% endif %}
""")


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def format_utc(ts: str | None) -> str:
    if not ts:
        return 'N/A'
    # Truncate to minute precision for readability
    return ts[:16].replace('T', ' ')


def query_date_range(conn, start: str, end: str) -> list:
    """Return patrol_final_results rows in [start, end)."""
    return conn.execute(
        '''SELECT *
           FROM patrol_final_results
           WHERE finished_at_utc >= ?
             AND finished_at_utc < ?
           ORDER BY finished_at_utc ASC''',
        (start, end),
    ).fetchall()


def compute_stats(rows):
    rows = [dict(r) for r in rows]
    decisions = [r['final_decision'] for r in rows]
    max_counts = [r['max_person_count'] for r in rows if r['max_person_count'] > 0]
    confs = [r['max_confidence'] for r in rows if r['max_confidence'] > 0]

    return {
        'total_rounds': len(rows),
        'occupied_count': decisions.count('occupied'),
        'empty_count': decisions.count('empty'),
        'uncertain_count': decisions.count('uncertain'),
        'total_observations': sum((r.get('scan_total_frames') or 0) for r in rows),
        'max_person_count': max(max_counts) if max_counts else 0,
        'avg_confidence': sum(confs) / len(confs) if confs else 0,
    }


def main():
    parser = argparse.ArgumentParser(description='Generate daily patrol report')
    parser.add_argument('--db', default=DEFAULT_DB, help=f'SQLite path (default: {DEFAULT_DB})')
    parser.add_argument('--date', help='Report date YYYY-MM-DD (default: today)')
    parser.add_argument('--days', type=int, default=1, help='Date range in days (default: 1)')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    args = parser.parse_args()

    db_path = str(resolve_workspace_path(args.db))
    if not os.path.isfile(db_path):
        print(f'Database not found: {db_path}', file=sys.stderr)
        sys.exit(1)

    # Resolve date range
    if args.date:
        try:
            report_date = datetime.strptime(args.date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            print(f'Invalid date: {args.date} (use YYYY-MM-DD)', file=sys.stderr)
            sys.exit(1)
        end_date = report_date + timedelta(days=1)
    else:
        # Today in UTC
        now = datetime.now(timezone.utc)
        report_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = report_date + timedelta(days=args.days)

    start_str = report_date.strftime('%Y-%m-%dT00:00:00')
    end_str = end_date.strftime('%Y-%m-%dT00:00:00')

    conn = connect(db_path)
    rows = query_date_range(conn, start_str, end_str)
    errors = [r for r in rows if r['error_msg']]

    stats = compute_stats(rows)
    occupied_records = [r for r in rows if r['final_decision'] == 'occupied']

    # Format rows for template
    def fmt_row(r):
        d = dict(r)
        d['finished_at'] = format_utc(d.get('finished_at_utc'))
        d['detector_backend'] = d.get('detector_backend', 'N/A')
        d['occupied_positions'] = d.get('occupied_positions', 'N/A')
        d['error_msg'] = d.get('error_msg', '')
        return d

    all_records = [fmt_row(r) for r in rows]
    occupied_records = [fmt_row(r) for r in occupied_records]
    errors = [fmt_row(r) for r in errors]

    backends = list({r.get('detector_backend', 'N/A') for r in all_records})

    date_label = report_date.strftime('%Y-%m-%d')
    if args.days > 1:
        date_label += f' ~ {end_date.strftime("%Y-%m-%d")}'

    rendered = REPORT_TEMPLATE.render(
        date_str=date_label,
        date_range=f'{start_str} → {end_str}',
        generated_at=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        db_path=db_path,
        stats=stats,
        all_records=all_records,
        occupied_records=occupied_records,
        errors=errors,
        backends=backends,
    )

    if args.output:
        Path(args.output).write_text(rendered)
        print(f'Report saved to {args.output}')
    else:
        print(rendered)


if __name__ == '__main__':
    main()
