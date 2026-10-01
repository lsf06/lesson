# -*- coding: utf-8 -*-
import os, re

d = r'd:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture'
path = os.path.join(d, 'server', 'templates', 'index.html')

with open(path, 'r', encoding='utf-8') as f:
    html = f.read()

# Boundaries
main_start = html.find('<div class="main">')
body_end = html.find('</body>')
html_end = html.rfind('</html>')

# Header: everything before main
header = html[:main_start]

# Script section: everything after </body> and before </html>
script_section = html[body_end+7:html_end]

print(f'Header: {len(header)} chars')
print(f'Script: {len(script_section)} chars')

# ================================================================
# Rebuild the <div class="main"> section
# ================================================================

tab_bar = '''        <div class="tab-bar">
            <button class="tab-btn active" data-tab="dashboard" onclick="switchTab('dashboard')">📊 仪表盘</button>
            <button class="tab-btn" data-tab="camera" onclick="switchTab('camera')">📷 图像采集</button>
            <button class="tab-btn" data-tab="nlp" onclick="switchTab('nlp')">🤖 自然语言助手</button>
            <button class="tab-btn" data-tab="history" onclick="switchTab('history')">📜 数据历史</button>
        </div>'''

scope_panel = '''            <div class="panel" id="scope-panel">
                <div class="panel-header">
                    <span class="title-text">&#9672; Oscilloscope (Acc X/Y/Z)</span>
                    <span class="badge" id="buffer-badge">BUFFER: 0 pts</span>
                </div>
                <div class="panel-body" style="position:relative;">
                    <div id="chart"></div>
                    <div class="no-data-overlay" id="no-data-overlay">
                        <div class="icon">&#128225;</div>
                        <div>Waiting for device data...</div>
                        <div style="font-size:0.75em;">Ensure ESP32 is connected &amp; sending</div>
                    </div>
                </div>
            </div>'''

cards_panel = '''            <div class="panel" id="cards-panel">
                <div class="panel-header">
                    <span class="title-text">&#9672; Real-Time Acceleration</span>
                    <span class="badge">QMA6100P</span>
                </div>
                <div class="panel-body">
                    <div class="cards-row">
                        <div class="val-card" id="card-ax">
                            <span class="axis-label ax">AX</span>
                            <span class="axis-val" id="ax" style="color:var(--col-ax);">0.00</span>
                            <span class="axis-unit">m/s&#178;</span>
                        </div>
                        <div class="val-card" id="card-ay">
                            <span class="axis-label ay">AY</span>
                            <span class="axis-val" id="ay" style="color:var(--col-ay);">0.00</span>
                            <span class="axis-unit">m/s&#178;</span>
                        </div>
                        <div class="val-card" id="card-az">
                            <span class="axis-label az">AZ</span>
                            <span class="axis-val" id="az" style="color:var(--col-az);">0.00</span>
                            <span class="axis-unit">m/s&#178;</span>
                        </div>
                    </div>
                </div>
            </div>'''

att_panel = '''            <div class="panel" id="att-panel">
                <div class="panel-header">
                    <span class="title-text">&#9672; 3D Device Attitude</span>
                    <span class="badge">Pitch / Roll</span>
                </div>
                <div class="panel-body">
                    <div class="att-body">
                        <div class="scene">
                            <div class="cube" id="cube">
                                <div class="cube-face front">ACCEL</div>
                                <div class="cube-face back"></div>
                                <div class="cube-face right">AX</div>
                                <div class="cube-face left">AX</div>
                                <div class="cube-face top">AZ</div>
                                <div class="cube-face bottom">AZ</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>'''

camera_panel = '''            <div class="panel" id="camera-panel">
                <div class="panel-header">
                    <span class="title-text">📷 图像采集</span>
                    <span class="badge" id="cam-badge" style="color:var(--orange);">📁 预存图片（回放）</span>
                </div>
                <div class="panel-body">
                    <div class="camera-actions">
                        <button class="cam-btn" id="capture-btn" onclick="captureImage()">📷 拍照</button>
                    </div>
                    <div class="cam-status idle" id="cam-status">💡 点击「拍照」采集图像</div>
                    <div class="image-area" id="image-area">
                        <div class="empty-hint">📸 点击上方按钮拍照</div>
                    </div>
                    <details class="image-history" id="image-history-section" style="margin-top:8px;flex-shrink:0;">
                        <summary style="cursor:pointer;font-size:.78em;color:var(--dim);padding:4px 0;">📵 图像历史记录 (点击展开)</summary>
                        <div class="history-list" id="camera-image-history-list" style="max-height:160px;overflow-y:auto;display:flex;flex-direction:column;gap:6px;padding:4px 0;"></div>
                    </details>
                </div>
            </div>'''

nlp_panel = '''            <div class="panel" id="nlp-panel">
                <div class="panel-header">
                    <span class="title-text">🔮 自然语言查询</span>
                    <span class="badge" id="nlp-badge">本地规则引擎</span>
                </div>
                <div class="panel-body">
                    <div class="chat-log" id="chat-log">
                        <div class="chat-msg bot">👋 你好！可以试试：<br>• "查看最新数据"<br>• "重新采集一次"</div>
                    </div>
                    <div class="voice-status idle" id="voice-status">🎙 待机</div>
                    <div class="chat-input-row">
                        <button id="voice-btn" class="voice-btn" onmousedown="startVoice()" onmouseup="stopVoice()" onmouseleave="stopVoice()">🎙 按住说话</button>
                        <input id="nlp-input" type="text" placeholder="例如：查看最新数据" onkeydown="if(event.key==='Enter')sendNlp()">
                        <button id="nlp-send-btn" onclick="sendNlp()">发送</button>
                        <button id="stop-btn" class="stop-btn" onclick="cancelNlp()" disabled>⏹ 停止</button>
                    </div>
                    <div class="time-metrics" id="time-metrics"></div>
                </div>
            </div>'''

history_tab = '''            <div class="tab-page" id="tab-history">
                <div class="hist-page">
                    <div class="sensor-history-panel">
                        <div class="panel-header">
                            <span class="title-text">📊 传感器数据历史</span>
                            <button onclick="loadSensorHistory()" style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:2px 10px;font-size:.75em;cursor:pointer;font-family:inherit;font-weight:600;">🔄 刷新</button>
                        </div>
                        <div class="sensor-table-wrap" id="sensor-table-wrap">
                            <div class="sensor-empty" id="sensor-empty">⏳ 加载中...</div>
                            <table class="sensor-table" id="sensor-table" style="display:none;">
                                <thead>
                                    <tr><th>#</th><th>AX</th><th>AY</th><th>AZ</th><th>时间</th></tr>
                                </thead>
                                <tbody id="sensor-tbody"></tbody>
                            </table>
                        </div>
                    </div>
                    <div class="image-history-panel">
                        <div class="panel-header">
                            <span class="title-text">📋 图像历史记录</span>
                        </div>
                        <div class="history-list" id="history-image-list" style="flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:6px;padding:8px;"></div>
                    </div>
                </div>
            </div>'''

# Build the complete main div
new_main = '''    <div class="main">
''' + tab_bar + '''
        <div class="tab-content">
            <div class="tab-page active" id="tab-dashboard">
                <div class="main-grid">
''' + scope_panel + '\n' + cards_panel + '\n' + att_panel + '''
                </div>
            </div>
            <div class="tab-page" id="tab-camera">
                <div style="height:100%;display:flex;flex-direction:column;">
''' + camera_panel + '''
                </div>
            </div>
            <div class="tab-page" id="tab-nlp">
                <div style="height:100%;display:flex;flex-direction:column;">
''' + nlp_panel + '''
                </div>
            </div>
''' + history_tab + '''
        </div>
    </div>'''

# Assemble final HTML
new_html = header + '\n' + new_main + '\n' + script_section + '\n</body>\n</html>'

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_html)

print(f'Written {len(new_html)} chars')
print('Done!')
