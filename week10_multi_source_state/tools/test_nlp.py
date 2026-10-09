# test_nlp.py — Week 4 NLP Agent 测试脚本
# 用法：先启动 flask（python app.py），然后运行本脚本
# python test_nlp.py

import json
import time
import sys
import requests

BASE = 'http://localhost:5000'

PASS = 0
FAIL = 0


def test(name, text, expect_tool, expect_success=True, expect_kw=None):
    """发送一条自然语言请求并断言。"""
    global PASS, FAIL
    print(f'\n▶ 测试: {name}')
    print(f'  输入: "{text}"')
    try:
        r = requests.post(f'{BASE}/api/nlp',
                          json={'text': text},
                          timeout=15)
        d = r.json()
    except Exception as e:
        print(f'  ❌ 请求异常: {e}')
        FAIL += 1
        return

    tool = d.get('tool_used') or ''
    success = d.get('success', False)
    reply = d.get('reply', '')[:80]

    print(f'  reply: {reply}')
    print(f'  tool: {tool}  success: {success}')

    ok = True

    # 检查 tool
    if expect_tool:
        if tool != expect_tool:
            print(f'  ❌ 期望 tool={expect_tool}，实际 tool={tool}')
            ok = False

    # 检查 success
    if expect_success is not None:
        if success != expect_success:
            print(f'  ❌ 期望 success={expect_success}，实际 success={success}')
            ok = False

    # 检查关键字
    if expect_kw:
        for kw in expect_kw:
            if kw not in (reply or ''):
                print(f'  ❌ 回复缺少关键字: "{kw}"')
                ok = False

    if ok:
        print(f'  ✅ PASS')
        PASS += 1
    else:
        FAIL += 1


def wait_for_flask(timeout=5):
    """等 Flask 就绪。"""
    for _ in range(timeout * 2):
        try:
            r = requests.get(f'{BASE}/api/count', timeout=2)
            if r.ok:
                print('✅ Flask 已就绪')
                return True
        except Exception:
            pass
        time.sleep(0.5)
    print('❌ Flask 未就绪，请先启动 python app.py')
    return False


if __name__ == '__main__':
    if not wait_for_flask():
        sys.exit(1)

    # ========== 用例 1: 正确查询 ==========
    test(
        name='正确查询——查看最新数据',
        text='查看 group01_esp32s3eye 的最新数据',
        expect_tool='tool_query_latest',
        expect_success=True,
        expect_kw=['设备', 'AX']
    )

    # ========== 用例 2: 正确查询（简单说法）==========
    test(
        name='正确查询——上一条记录',
        text='上一条记录是什么',
        expect_tool='tool_query_latest',
        expect_success=True,
    )

    # ========== 用例 3: 正确采集 ==========
    test(
        name='正确采集——重新采集',
        text='帮 group01_esp32s3eye 重新采集一次',
        expect_tool='tool_request_collection',
        expect_success=None,  # 取决于硬件是否在线
    )

    # ========== 用例 4: 含糊——代词指代不明 ==========
    test(
        name='含糊——查一下那个东西',
        text='查一下那个东西',
        expect_tool=None,
        expect_success=True,
        expect_kw=['请问']  # 必须反问用户
    )

    # ========== 用例 5: 含糊——无设备无意图 ==========
    test(
        name='含糊——乱七八糟的输入',
        text='今天天气不错',
        expect_tool=None,
        expect_success=True,
        expect_kw=['理解']  # 应提示不理解意图
    )

    # ========== 用例 6: 越界设备 ==========
    test(
        name='越界——查 group99_fake 的数据',
        text='查一下 group99_fake 的最新数据',
        expect_tool=None,
        expect_success=False,
        expect_kw=['白名单']
    )

    # ========== 用例 7: 纯采集意图 ==========
    test(
        name='采集——帮我测一下',
        text='帮我测一下现在的数据',
        expect_tool='tool_request_collection',
        expect_success=None,
    )

    # ========== 用例 8: 采集——测一下 ==========
    test(
        name='采集——测一下 group01_esp32s3eye',
        text='测一下 group01_esp32s3eye',
        expect_tool='tool_request_collection',
        expect_success=None,
    )

    # ========== 总结 ==========
    print(f'\n{"=" * 45}')
    print(f'  测试完成：{PASS} PASS / {FAIL} FAIL  (共 {PASS + FAIL} 个)')
    print(f'{"=" * 45}')
    if FAIL:
        sys.exit(1)
    else:
        sys.exit(0)