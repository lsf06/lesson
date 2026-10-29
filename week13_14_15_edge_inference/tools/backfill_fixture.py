#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# tools/backfill_fixture.py —— 第14周补传闭环的「状态注入」验证工具
#
# 【这不是实物断网实验】
# 本脚本不拔网线、不关热点，也不驱动 ESP32。它通过**真实 HTTP 接口**
# POST /api/upload 提交 original_ts 明显早于 retransmit_ts 的数据，
# 让服务端按 week13_14_15_edge_inference/server/app.py:356-367 的既有规则
# 自行判出 delivery_status='recovered'，并带上 data_origin='simulated'。
#
# 它能证明：接口契约、服务端判定、落库字段、/api/history 回吐字段、前端徽章数据源 全部连通。
# 它不能证明：设备端环形缓存在真实断网时确实缓存并补传（那需要实物复测）。
#
# 用法：
#   python tools/backfill_fixture.py --url http://127.0.0.1:5000 --count 3 --delay 45

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def post_json(url, payload, timeout=10):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode('utf-8'))


def get_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def main():
    ap = argparse.ArgumentParser(description='Inject recovered-delivery fixture rows via /api/upload')
    ap.add_argument('--url', default='http://127.0.0.1:5000')
    ap.add_argument('--device', default='group01_esp32s3eye')
    ap.add_argument('--count', type=int, default=3)
    ap.add_argument('--delay', type=int, default=45, help='seconds between original_ts and retransmit_ts')
    args = ap.parse_args()

    if args.delay <= 30:
        print('[FATAL] --delay 必须 > 30，否则服务端会判回 live（app.py:361）')
        return 2

    now = int(time.time())
    sent = []
    for i in range(args.count):
        orig = now - args.delay - i
        payload = {
            'device_id': args.device,
            'ax': round(0.10 + i * 0.01, 3),
            'ay': round(-0.20 - i * 0.01, 3),
            'az': round(9.81 + i * 0.01, 3),
            'device_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(orig)),
            'original_ts': orig,
            'retransmit_ts': now,
            'data_origin': 'simulated',
        }
        status, body = post_json(args.url + '/api/upload', payload)
        print('[POST] /api/upload status=%s original_ts=%s retransmit_ts=%s -> %s'
              % (status, orig, now, json.dumps(body, ensure_ascii=True)))
        sent.append(orig)

    hist = get_json(args.url + '/api/history?count=100')
    rows = hist.get('records', [])
    mine = [r for r in rows if r.get('original_ts') in sent]

    print()
    print('=== /api/history 回吐（仅本次注入行）===')
    head = 'original_ts | retransmit_ts | delivery_status | data_origin'
    print(head)
    print('-' * len(head))
    for r in mine:
        print('%11s | %13s | %15s | %s'
              % (r.get('original_ts'), r.get('retransmit_ts'),
                 r.get('delivery_status'), r.get('data_origin')))

    ok = True
    if len(mine) != args.count:
        print('[FAIL] 期望回吐 %d 行，实际 %d 行' % (args.count, len(mine)))
        ok = False
    for r in mine:
        if r.get('delivery_status') != 'recovered':
            print('[FAIL] original_ts=%s 的 delivery_status=%s，不是 recovered'
                  % (r.get('original_ts'), r.get('delivery_status')))
            ok = False
        if r.get('data_origin') != 'simulated':
            print('[FAIL] original_ts=%s 的 data_origin=%s，不是 simulated'
                  % (r.get('original_ts'), r.get('data_origin')))
            ok = False

    print()
    if ok:
        print('PASS: %d 行均为 delivery_status=recovered + data_origin=simulated' % len(mine))
        print('注意：这是状态注入结果，前端会显示「🧪 注入样例」标记；实物断网补传仍未验证。')
        return 0
    print('FAIL: 注入校验未通过')
    return 1


if __name__ == '__main__':
    sys.exit(main())
