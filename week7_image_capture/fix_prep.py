# -*- coding: utf-8 -*-
import os
d = r'd:\lesson\xiaolin\lesson-main (1)\lesson-main\week7_image_capture'
path = os.path.join(d, 'server', 'templates', 'index.html')
with open(path, 'r', encoding='utf-8') as f:
    html = f.read()
print('Read', len(html), 'chars')
body_start = html.find('<body>')
main_start = html.find('<div class="main">')
body_end = html.find('</body>')
print(f'body={body_start} main={main_start} body_end={body_end}')
# Everything before main start is header section
header = html[:main_start]
# The content after </body> is the script section (which is currently misplaced)
after_body = html[body_end+7:]
print(f'After body: {repr(after_body[:80])}')
# The main content needs to be replaced
# Find where the main div ends (before the misplaced </body>)
pre_body = html[main_start:body_end]
# Find the last </div> in the main section
last_div = pre_body.rstrip().rfind('</div>')
print(f'Main content ends at offset {last_div} from main_start')
main_content_before_script = pre_body[:last_div+6]
print(f'Main content length: {len(main_content_before_script)}')
# Find </html>
html_end = html.rfind('</html>')
print(f'</html> at {html_end}')
# The complete script section
all_after = html[body_end+7:html_end]
print(f'All after body: {len(all_after)} chars')
print(f'Starts with: {repr(all_after[:80])}')
print('DONE')
