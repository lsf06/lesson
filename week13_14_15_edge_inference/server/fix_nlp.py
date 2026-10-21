#!/usr/bin/env python3
import re, sys

FILE = "app.py"

with open(FILE, encoding="utf-8") as f:
    data = f.read()

# ---- Build replacement ----
L = []  # list of lines

def add(*args):
    for a in args:
        L.append(a)

add("# ====== Week 4: NLP Agent =====")
add("")
add("VALID_DEVICES = ['group01_esp32s3eye']")
add("")
add("NLP_TOOLS = [")
add("    {'type':'function','function':{'name':'tool_query_latest',"
    "'description':'Query the latest sensor data (ax, ay, az) and timestamp for a specified device',"
    "'parameters':{'type':'object','properties':{'device_id':{'type':'string',"
    "'description':'Device ID, e.g. group01_esp32s3eye'}},'required':['device_id']}}},")
add("    {'type':'function','function':{'name':'tool_request_collection',"
    "'description':'Initiate a new data collection request for a specified device',"
    "'parameters':{'type':'object','properties':{'device_id':{'type':'string',"
    "'description':'Device ID, e.g. group01_esp32s3eye'}},'required':['device_id']}}}")
add("]")
add("")
add("SYSTEM_PROMPT = (")
add("    'You are a sensor data query assistant. Only use tool_query_latest or tool_request_collection.\\n'")
add("    'device_id must be explicit, not ambiguous. Only valid device_id is group01_esp32s3eye.\\n'")
add('    \'Output strict JSON: {"intent":"tool_query_latest","device_id":"group01_esp32s3eye","ambiguous":false} \\n\'')
add('    \'If ambiguous: {"intent":"","device_id":"","ambiguous":true,"message":"Please specify which device you want to query."}\'')
add(")")
add("")
add("")
add("def _local_nlp_parse(text):")
add('    """Local rule-based parser: keyword matching for Chinese input."""')
add("    t = text.lower().strip()")
add("")
add("    # 1. Extract device_id")
add("    fdev = None")
add("    for d in VALID_DEVICES:")
add("        if d.lower() in t:")
add("            fdev = d")
add("            break")
add("")
add("    # 2. Check unknown device IDs")
add("    cids = re.findall(r'(group\\d+_?\\w*|esp32\\w*|device_\\w+)', t, re.I)")
add("    for cid in cids:")
add("        if cid.lower() not in [x.lower() for x in VALID_DEVICES]:")
add("            return {'intent':'','device_id':'','ambiguous':False,'rejected':True,")
add('                    \'reject_msg\':f\'Device "{cid}" not in whitelist. Available: {", ".join(VALID_DEVICES)}\'}')
add("")
add("    # 3. Ambiguity")
add("    amb = ['" + "','".join(["\\u54ea\\u4e2a","\\u4ec0\\u4e48","\\u968f\\u4fbf","\\u8fd9","\\u90a3","\\u6240\\u6709","\\u5168\\u90e8","\\u4efb\\u4f55"]) + "']")
add("    if any(w in t for w in amb) and not fdev:")
add("        return {'intent':'','device_id':'','ambiguous':True,")
add('                \'message\':f\'Please specify which device. Available: {", ".join(VALID_DEVICES)}\'}')
add("")
add("    # 4. Classify intent (Chinese keywords)")
add("    qkw = ['" + "','".join(["\\u67e5\\u770b","\\u67e5\\u8be2","\\u6700\\u65b0","\\u4e0a\\u6b21","\\u6570\\u636e","\\u4e0a\\u4e00\\u6761"]) + "']")
add("    ckw = ['" + "','".join(["\\u91c7\\u96c6","\\u91cd\\u65b0","\\u6d4b","\\u62cd\\u7167","\\u770b\\u770b","capture"]) + "']")
add("")
add("    is_q = any(k in t for k in qkw)")
add("    is_c = any(k in t for k in ckw)")
add("")
add("    if is_c and not is_q:")
add("        intent = 'tool_request_collection'")
add("    elif is_q:")
add("        intent = 'tool_query_latest'")
add("    elif is_c:")
add("        intent = 'tool_request_collection'")
add("    elif fdev:")
add("        intent = 'tool_query_latest'")
add("    else:")
add("        return {'intent':'','device_id':'','ambiguous':True,")
add('                \'message\':\'Sorry, I did not understand your intent. Try "check latest data" or "re-collect".\'}')
add("")
add("    if not fdev:")
add("        fdev = VALID_DEVICES[0]")
add("")
add("    return {'intent':intent,'device_id':fdev,'ambiguous':False,'rejected':False}")
add("")
add("")
add("def _llm_nlp_parse(text):")
add('    """LLM API parser: call OpenAI-compatible API to parse natural language."""')
add("    try:")
add("        resp = _openai_client.chat.completions.create(")
add("            model='deepseek-chat',")
add("            messages=[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':text}],")
add("            tools=NLP_TOOLS, tool_choice='auto', temperature=0.1, max_tokens=300")
add("        )")
add("        msg = resp.choices[0].message")
add("        if msg.tool_calls:")
add("            tc = msg.tool_calls[0]")
add("            func_name = tc.function.name")
add("            import json as _j")
add("            args = _j.loads(tc.function.arguments) if tc.function.arguments else {}")
add("            did = args.get('device_id','')")
add("            if did not in VALID_DEVICES:")
add("                return {'intent':'','device_id':'','ambiguous':False,'rejected':True,")
add('                        \'reject_msg\':f\'Device "{did}" not in whitelist.\'}')
add("            return {'intent':func_name,'device_id':did,'ambiguous':False,'rejected':False}")
add("        content = (msg.content or '').strip()")
add("        if content.startswith('```'):")
add("            content = re.sub(r'^```(?:json)?\\s*','',content)")
add("            content = re.sub(r'\\s*```$','',content)")
add("        try:")
add("            import json as _j")
add("            result = _j.loads(content)")
add("        except Exception:")
add("            result = {}")
add("        if result.get('ambiguous'):")
add("            return {'intent':'','device_id':'','ambiguous':True,")
add('                    \'message\':result.get(\'message\',\'Please specify which device you want to query.\')}')
add("        did = result.get('device_id','')")
add("        intent = result.get('intent','')")
add("        if did not in VALID_DEVICES:")
add("            return {'intent':'','device_id':'','ambiguous':False,'rejected':True,")
add('                    \'reject_msg\':f\'Device "{did}" not in whitelist.\'}')
add("        if intent not in ('tool_query_latest','tool_request_collection'):")
add("            return {'intent':'','device_id':'','ambiguous':True,'message':'Sorry, I did not understand your intent.'}")
add("        return {'intent':intent,'device_id':did,'ambiguous':False,'rejected':False}")
add("    except Exception as e:")
add("        log.warning('LLM API call failed: %s, falling back to local parser', e)")
add("        return _local_nlp_parse(text)")
add("")
add("")

replacement = "\n".join(L) + "\n"

# ---- Find markers ----
m_start = re.search(r'^#.*Week 4.*NLP Agent.*$', data, re.MULTILINE)
if not m_start:
    # Search garbled version
    m_start = re.search(r'#.*Week 4.*NLP Agent', data)
m_end = re.search(r"@app\.route\('/api/cancel_nlp'", data)

assert m_start, "Cannot find start marker"
assert m_end, "Cannot find end marker"

start = m_start.start()
end = m_end.start()
print(f"NLP section: bytes {start}-{end}")

new_data = data[:start] + replacement + data[end:]

with open(FILE, "w", encoding="utf-8", newline="\n") as f:
    f.write(new_data)

print("Written. Validating...")

# Verify Chinese keywords
for cjk in ["\u67e5\u770b","\u67e5\u8be2","\u6700\u65b0","\u4e0a\u6b21",
            "\u6570\u636e","\u4e0a\u4e00\u6761",
            "\u91c7\u96c6","\u91cd\u65b0","\u6d4b","\u62cd\u7167","\u770b\u770b",
            "\u54ea\u4e2a","\u4ec0\u4e48","\u968f\u4fbf","\u8fd9","\u90a3",
            "\u6240\u6709","\u5168\u90e8","\u4efb\u4f55"]:
    if cjk not in new_data:
        print(f"WARNING: Chinese char U+{ord(cjk):04X} missing!")
    else:
        print(f"  OK: Chinese char U+{ord(cjk):04X} ({cjk})")

import ast
ast.parse(new_data)
print("Syntax OK!")
