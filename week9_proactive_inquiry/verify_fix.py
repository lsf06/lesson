# -*- coding: utf-8 -*-
import os
d = r'd:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture'
with open(os.path.join(d, 'server', 'templates', 'index.html'), 'r', encoding='utf-8') as f:
    body = f.read()

checks = {}
checks['<!DOCTYPE>'] = '<!DOCTYPE' in body
checks['</html>'] = '</html>' in body
checks['</body> before </html>'] = body.rfind('</body>') < body.rfind('</html>')
checks['<script> before </body>'] = body.rfind('<script>') < body.rfind('</body>')
checks['tab-bar class'] = 'class="tab-bar"' in body
checks['tab-btn count'] = body.count('tab-btn')
checks['tab-page count'] = body.count('tab-page')
checks['main-grid'] = 'class="main-grid"' in body
checks['scope-panel'] = 'id="scope-panel"' in body
checks['cards-panel'] = 'id="cards-panel"' in body
checks['att-panel'] = 'id="att-panel"' in body
checks['camera-panel'] = 'id="camera-panel"' in body
checks['nlp-panel'] = 'id="nlp-panel"' in body
checks['tab-history'] = 'id="tab-history"' in body
checks['sensor-table'] = 'sensor-table' in body
checks['echarts.init'] = 'echarts.init' in body
checks['MAX_POINTS=200'] = 'var MAX_POINTS=200' in body
checks['loadSensorHistory'] = 'loadSensorHistory' in body
checks['switchTab'] = 'switchTab' in body

div_opens = body.count('<div')
div_closes = body.count('</div>')
checks['div balance'] = div_opens == div_closes
checks['div diff'] = div_opens - div_closes

for k, v in checks.items():
    status = 'OK' if v else 'FAIL'
    print(f'  [{status}] {k}: {v}')

# In-depth: check panel order in body before script
script_pos = body.find('<script>')
if script_pos > 0:
    html_before_script = body[:script_pos]
    main_start = html_before_script.find('class="main"')
    # find panels
    sp = html_before_script.find('scope-panel')
    cp = html_before_script.find('cards-panel')
    ap = html_before_script.find('att-panel')
    print(f'\nPanel positions in HTML (before script):')
    print(f'  scope: {sp}, cards: {cp}, att: {ap}')
    if sp < cp < ap:
        print('  ORDER OK - scope < cards < att')
    else:
        print('  ORDER WRONG')

    # Check if they are siblings (each inside main-grid)
    # Find main-grid content
    mg = html_before_script.find('main-grid')
    mg_end = html_before_script.find('</div>', mg+50)
    if mg > 0 and mg_end > 0:
        grid_html = html_before_script[mg:mg_end+60]
        print(f'\nMain-grid contains scope: {"scope-panel" in grid_html}')
        print(f'Main-grid contains cards: {"cards-panel" in grid_html}')
        print(f'Main-grid contains att: {"att-panel" in grid_html}')
        
        # Check if panels are proper siblings by finding panel open/close pattern
        s_open = grid_html.count('<div class="panel" id="scope-panel"')
        c_open = grid_html.count('<div class="panel" id="cards-panel"')
        a_open = grid_html.count('<div class="panel" id="att-panel"')
        print(f'\nPanel opening tags in grid: scope={s_open}, cards={c_open}, att={a_open}')
        if s_open == 1 and c_open == 1 and a_open == 1:
            print('  STRUCTURE OK - each panel opens exactly once')
        else:
            print('  STRUCTURE WRONG - panel count mismatch')

print('\nFile size:', len(body), 'bytes')
