#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 第17周：心率场景迁移 —— 环形缓存 + 双时间戳补传 仿真验证
#
# 【证据等级声明】本脚本是纯软件仿真，不连接 MAX30102，也不连接服务器。
# 它只复刻第14周已实现的判定逻辑，用来说明迁移方案在设计层面成立；
# 不能作为心率采集硬件、也不能作为设备端补传的实测证据。
#
# 复刻来源：
#   1) 固件环形队列 week13_14_15_edge_inference/esp32_firmware/main/main.c
#        :92        #define CACHE_QUEUE_SIZE 20
#        :377-388   cache_enqueue()  队列满丢最旧，打印 QUEUE FULL, dropped oldest record
#   2) 服务端判定   week13_14_15_edge_inference/server/app.py
#        :356-367   retransmit_ts>0 且 (original_ts<=0 或 delay>30s) -> delivery_status=recovered
#
# 用法：python heart_rate_simulator.py
import time
from dataclasses import dataclass
from typing import List

QUEUE_SIZE = 20           # 对齐 main.c:92
RECOVER_THRESHOLD_S = 30  # 对齐 app.py:361


@dataclass
class HeartRecord:
    seq: int
    heart_rate: int
    original_ts: float
    retransmit_ts: float = 0.0
    delay_s: float = 0.0
    delivery_status: str = 'live'


class RingCache:
    # 对应固件 g_cache / g_cache_head / g_cache_count（main.c:102、377-388）

    def __init__(self, size: int = QUEUE_SIZE):
        self.size = size
        self.items: List[HeartRecord] = []
        self.dropped = 0

    def __len__(self):
        return len(self.items)

    def enqueue(self, rec: HeartRecord) -> None:
        if len(self.items) >= self.size:
            old = self.items.pop(0)
            self.dropped += 1
            print('[WARN] QUEUE FULL, dropped oldest record: seq=%d hr=%d'
                  % (old.seq, old.heart_rate))
        self.items.append(rec)
        print('[INFO] Cached locally (queue=%d/%d) hr=%d bpm'
              % (len(self.items), self.size, rec.heart_rate))

    def flush(self, now: float) -> List[HeartRecord]:
        # 补传：写入 retransmit_ts 并按服务端规则重算 delivery_status
        out = []
        for rec in self.items:
            rec.retransmit_ts = now
            rec.delay_s = now - rec.original_ts
            if rec.retransmit_ts > 0 and (rec.original_ts <= 0
                                          or rec.delay_s > RECOVER_THRESHOLD_S):
                rec.delivery_status = 'recovered'
            else:
                rec.delivery_status = 'live'
            out.append(rec)
        self.items = []
        return out


def hhmmss(ts: float) -> str:
    return time.strftime('%H:%M:%S', time.localtime(ts))


def print_table(rows: List[HeartRecord]) -> None:
    head = 'seq | hr_bpm | original_ts | retransmit_ts | delay_s | delivery_status'
    print(head)
    print('-' * len(head))
    for r in rows:
        print('%3d | %6d | %11s | %13s | %7.1f | %s'
              % (r.seq, r.heart_rate, hhmmss(r.original_ts),
                 hhmmss(r.retransmit_ts) if r.retransmit_ts else '-',
                 r.delay_s, r.delivery_status))


def main() -> int:
    t0 = time.mktime(time.localtime()[:3] + (9, 0, 0, 0, 0, -1))
    live: List[HeartRecord] = []
    cache = RingCache(QUEUE_SIZE)
    seq = 0

    print('=== 阶段1：网络正常，心率 1Hz 直传（delivery_status=live）===')
    for i in range(5):
        seq += 1
        rec = HeartRecord(seq=seq, heart_rate=70 + i, original_ts=t0 + i,
                          retransmit_ts=0.0, delay_s=0.0, delivery_status='live')
        live.append(rec)
        print('[INFO] POST /api/upload hr=%d original_ts=%s -> live'
              % (rec.heart_rate, hhmmss(rec.original_ts)))

    print()
    print('=== 阶段2：断网 3 拍，写入环形队列（不发送）===')
    offline_start = t0 + 6
    for i in range(3):
        seq += 1
        cache.enqueue(HeartRecord(seq=seq, heart_rate=72 + i * 3,
                                  original_ts=offline_start + i))

    print()
    print('=== 阶段3：网络恢复，补传（delay>30s 判 recovered）===')
    now = offline_start + 38
    recovered = cache.flush(now)
    for r in recovered:
        print('[INFO] POST /api/upload hr=%d original_ts=%s retransmit_ts=%s delay=%.1fs -> %s'
              % (r.heart_rate, hhmmss(r.original_ts), hhmmss(r.retransmit_ts),
                 r.delay_s, r.delivery_status))

    print()
    print('=== 阶段4：长时间断网，25 拍灌入 20 槽队列（验证丢最旧）===')
    cache2 = RingCache(QUEUE_SIZE)
    for i in range(25):
        seq += 1
        cache2.enqueue(HeartRecord(seq=seq, heart_rate=60 + i, original_ts=now + 1 + i))
    now2 = now + 200
    recovered2 = cache2.flush(now2)
    print('[INFO] flush -> %d 条补传记录，丢弃 %d 条最旧记录'
          % (len(recovered2), cache2.dropped))

    print()
    print('=== 计数口径（逐项可核对，不是自证）===')
    print('[COUNT] 样本总数 seq=%d = 阶段1 %d(live) + 阶段2 %d(进队列) + 阶段4 灌入 %d'
          % (seq, len(live), len(recovered), len(recovered2) + cache2.dropped))
    print('[COUNT] recovered=%d = 阶段3 补传 %d + 阶段4 补传 %d'
          % (len(recovered + recovered2), len(recovered), len(recovered2)))
    print('[COUNT] 阶段4：灌入 %d = 入队 %d + 丢弃最旧 %d'
          % (len(recovered2) + cache2.dropped, len(recovered2), cache2.dropped))
    print('[COUNT] live=%d（阶段1 直传，retransmit_ts=0）' % len(live))

    print()
    print('=== 结果表 ===')
    print_table(live + recovered + recovered2)

    print()
    print('=== 断言 ===')
    assert len(cache2) == 0 and len(cache) == 0, 'flush 后队列必须清空'
    assert all(r.delivery_status == 'live' and r.retransmit_ts == 0 for r in live), \
        '实时记录不得被标成补传'
    assert all(r.delivery_status == 'recovered' and r.retransmit_ts > r.original_ts
               for r in recovered + recovered2), '补传记录必须为 recovered 且时间戳递增'
    assert all(r.delay_s > RECOVER_THRESHOLD_S for r in recovered + recovered2), \
        '补传延迟必须超过阈值，否则服务端会判回 live'
    assert cache2.dropped == 5, '25 拍灌入 20 槽应丢弃 5 条'
    assert len(recovered2) == QUEUE_SIZE, '补传条数必须等于队列容量'
    assert seq == 33, '样本次数应为 5 + 3 + 25'
    print('ALL ASSERTIONS PASSED (live=%d, recovered=%d, dropped=%d)'
          % (len(live), len(recovered + recovered2), cache2.dropped))
    print()
    print('说明：本输出是仿真结果，仅证明队列/时间戳/状态机逻辑成立；')
    print('      不代表已连接 MAX30102 实物，也不代表设备端真实断网补传已通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
