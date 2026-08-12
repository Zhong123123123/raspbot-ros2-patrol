#!/usr/bin/env python3

import argparse
import csv
import os
import sqlite3
import sys
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Query patrol final results or per-angle observations from SQLite.',
    )
    parser.add_argument('--db', default='~/ros2_ws/data/patrol/patrol_events.db', help='SQLite database path.')
    parser.add_argument('--mode', choices=['final', 'observations'], default='final', help='Query final patrol summary or per-angle observations.')
    parser.add_argument('--limit', type=int, default=10, help='Maximum rows to return.')
    parser.add_argument('--decision', choices=['occupied', 'empty', 'uncertain'], help='Filter final results by final_decision. Only valid in final mode.')
    parser.add_argument('--detected', choices=['true', 'false'], help='Filter observations by detected state. Only valid in observations mode.')
    parser.add_argument('--detector-backend', dest='detector_backend', help='Filter by detector backend, such as hog or opencv_dnn_tf_ssd.')
    parser.add_argument('--from-time', dest='from_time', help='Inclusive lower bound of UTC/local timestamp string.')
    parser.add_argument('--to-time', dest='to_time', help='Inclusive upper bound of UTC/local timestamp string.')
    parser.add_argument('--patrol-id', help='Filter by specific patrol_id.')
    parser.add_argument('--csv', dest='csv_path', help='Export query result to CSV file.')
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.limit <= 0:
        raise SystemExit('--limit must be > 0')
    if args.decision and args.mode != 'final':
        raise SystemExit('--decision can only be used with --mode final')
    if args.detected and args.mode != 'observations':
        raise SystemExit('--detected can only be used with --mode observations')


def build_query(args: argparse.Namespace) -> tuple[str, list]:
    if args.mode == 'final':
        columns = [
            'patrol_id',
            'final_decision',
            'detected',
            'positive_observation_count',
            'total_observation_count',
            'max_person_count',
            'ROUND(max_confidence, 2) AS max_confidence',
            'occupied_positions',
            'detector_backend',
            'decision_reason',
            'finished_at_utc',
        ]
        table = 'patrol_final_results'
        order_column = 'finished_at_utc'
    else:
        columns = [
            'patrol_id',
            'scan_position',
            'detected',
            'person_count',
            'ROUND(max_confidence, 2) AS max_confidence',
            'scan_positive_frames',
            'scan_total_frames',
            'detector_backend',
            'error_msg',
            'raw_image_path',
            'debug_image_path',
            'timestamp_utc',
        ]
        table = 'patrol_observations'
        order_column = 'timestamp_utc'

    conditions = []
    params: list = []

    if args.patrol_id:
        conditions.append('patrol_id = ?')
        params.append(args.patrol_id)

    if args.detector_backend:
        conditions.append('detector_backend LIKE ?')
        params.append(f'%{args.detector_backend}%')

    if args.from_time:
        conditions.append(f'{order_column} >= ?')
        params.append(args.from_time)

    if args.to_time:
        conditions.append(f'{order_column} <= ?')
        params.append(args.to_time)

    if args.mode == 'final' and args.decision:
        conditions.append('final_decision = ?')
        params.append(args.decision)

    if args.mode == 'observations' and args.detected:
        conditions.append('detected = ?')
        params.append(1 if args.detected == 'true' else 0)

    where_sql = ''
    if conditions:
        where_sql = 'WHERE ' + ' AND '.join(conditions)

    sql = f'''
SELECT
  {", ".join(columns)}
FROM {table}
{where_sql}
ORDER BY {order_column} DESC
LIMIT ?
'''
    params.append(args.limit)
    return sql, params


def stringify(value) -> str:
    if value is None:
        return ''
    return str(value)


def print_table(headers: list[str], rows: Iterable[tuple]) -> None:
    rows = [tuple(stringify(v) for v in row) for row in rows]
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def fmt_row(values: Iterable[str]) -> str:
        return '  '.join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    print(fmt_row(headers))
    print('  '.join('-' * width for width in widths))
    for row in rows:
        print(fmt_row(row))


def export_csv(csv_path: str, headers: list[str], rows: list[tuple]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    validate_args(args)
    db_path = os.path.expanduser(args.db)
    if not os.path.isfile(db_path):
        print(f'database not found: {db_path}', file=sys.stderr)
        return 1

    sql, params = build_query(args)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()
        headers = [item[0] for item in cursor.description]
    finally:
        conn.close()

    print_table(headers, rows)
    if args.csv_path:
        export_csv(os.path.expanduser(args.csv_path), headers, rows)
        print(f'\nexported_csv: {os.path.expanduser(args.csv_path)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
