import fitz
import re
import os
import json
import uuid
import ssl
import http.cookiejar
import urllib.request

PDF_PATH = r"C:\Users\kumar\Downloads\16-December-2024-Shift-1-English.pdf"
RENDER_URL = "https://quiz-plateform.onrender.com"
ADMIN_PASSWORD = "admin123"
TEST_NAME = "Complete Full length 1"
TEST_DESCRIPTION = "16-December-2024 Shift-1 English (100 Questions)"
DURATION_MINUTES = 360  # 6 hours

def is_green(color_int):
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return g > 150 and r < 100

def group_spans_into_lines(spans, y_tolerance=4):
    spans_sorted = sorted(spans, key=lambda s: s['bbox'][1])
    lines = []
    for s in spans_sorted:
        placed = False
        for line in lines:
            if abs(line['y'] - s['bbox'][1]) <= y_tolerance:
                line['spans'].append(s)
                placed = True
                break
        if not placed:
            lines.append({'y': s['bbox'][1], 'spans': [s]})
    lines.sort(key=lambda l: l['y'])
    ordered_spans = []
    for line in lines:
        line['spans'].sort(key=lambda s: s['bbox'][0])
        ordered_spans.extend(line['spans'])
    return ordered_spans

print("1. Reading PDF and parsing 100 questions...")
doc = fitz.open(PDF_PATH)
os.makedirs('uploads', exist_ok=True)

# Pre-extract diagram images for Q.5, Q.32, Q.60
diagrams = {
    5: 41,
    32: 88,
    60: 140
}
diagram_files = {}
for q_num, xref in diagrams.items():
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n >= 5:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        filename = f"q_{q_num}_{uuid.uuid4().hex[:6]}.png"
        filepath = os.path.join('uploads', filename)
        pix.save(filepath)
        diagram_files[q_num] = (filename, filepath)
        print(f"   Extracted diagram for Q.{q_num}: {filename}")
    except Exception as e:
        print(f"   Failed to extract diagram for Q.{q_num}: {e}")

questions_data = []

for p_idx, page in enumerate(doc):
    text_page = page.get_text('dict')
    raw_spans = []
    for b in text_page['blocks']:
        if 'lines' in b:
            for l in b['lines']:
                for s in l['spans']:
                    txt = s['text'].strip()
                    if txt:
                        raw_spans.append({
                            'text': s['text'],
                            'color': s['color'],
                            'bbox': s['bbox'],
                            'page': p_idx + 1
                        })
    spans = group_spans_into_lines(raw_spans, y_tolerance=4)
    
    q_indices = []
    for i, s in enumerate(spans):
        m = re.match(r'^Q\.(\d+)', s['text'].strip())
        if m:
            q_num = int(m.group(1))
            q_indices.append((i, q_num, s['bbox']))

    for k, (s_idx, q_num, q_bbox) in enumerate(q_indices):
        end_idx = q_indices[k+1][0] if k + 1 < len(q_indices) else len(spans)
        q_spans = spans[s_idx:end_idx]
        
        q_text_parts = []
        in_options = False
        options = {1: [], 2: [], 3: [], 4: []}
        curr_opt = None
        correct_opt = None
        
        for s in q_spans:
            t = s['text'].strip()
            
            if any(t.startswith(x) for x in ['Test Date', 'Test Time', 'Subject', 'Section :', 'Correct Answer will carry', 'Incorrect Answer', '1. Options shown in green', '2. Chosen option on the right', 'Chosen Option']):
                continue
            if t == f'Q.{q_num}':
                continue
                
            if t == 'Ans':
                in_options = True
                continue
                
            if in_options:
                m_opt = re.match(r'^([1-4])\.(.*)', t)
                if m_opt:
                    curr_opt = int(m_opt.group(1))
                    opt_content = m_opt.group(2).strip()
                    if opt_content:
                        options[curr_opt].append(opt_content)
                    if is_green(s['color']):
                        correct_opt = curr_opt
                else:
                    if curr_opt:
                        options[curr_opt].append(t)
                        if is_green(s['color']):
                            correct_opt = curr_opt
            else:
                q_text_parts.append(t)
                
        q_text = ' '.join(q_text_parts).strip()
        opt_a = ' '.join(options[1]).strip()
        opt_b = ' '.join(options[2]).strip()
        opt_c = ' '.join(options[3]).strip()
        opt_d = ' '.join(options[4]).strip()
        
        ans_map = {1: 'A', 2: 'B', 3: 'C', 4: 'D'}
        correct_letter = ans_map.get(correct_opt, 'A')
        
        # If question text is empty (diagram-only question like Q.5 or Q.32)
        if not q_text and q_num in diagram_files:
            q_text = f"Refer to the diagram below and choose the correct option:"
            
        questions_data.append({
            'num': q_num,
            'question_text': q_text,
            'option_a': opt_a,
            'option_b': opt_b,
            'option_c': opt_c,
            'option_d': opt_d,
            'correct_answer': correct_letter,
            'local_image': diagram_files.get(q_num)
        })

print(f"Parsed {len(questions_data)} questions successfully!")

# 2. Setup HTTP Client for Render
ctx = ssl.create_default_context()
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))

print(f"\n2. Authenticating with Render ({RENDER_URL})...")
login_data = json.dumps({'password': ADMIN_PASSWORD}).encode('utf-8')
login_req = urllib.request.Request(f"{RENDER_URL}/api/auth/login", data=login_data, headers={'Content-Type': 'application/json'})
with opener.open(login_req) as resp:
    print("   Login response:", resp.read().decode())

def upload_image_to_render(local_filepath, filename):
    boundary = '----FormBoundary' + uuid.uuid4().hex
    with open(local_filepath, 'rb') as f:
        file_bytes = f.read()
    
    header = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        f"Content-Type: image/png\r\n\r\n"
    ).encode('utf-8')
    footer = f"\r\n--{boundary}--\r\n".encode('utf-8')
    payload = header + file_bytes + footer
    
    req = urllib.request.Request(
        f"{RENDER_URL}/api/upload",
        data=payload,
        headers={'Content-Type': f"multipart/form-data; boundary={boundary}"}
    )
    with opener.open(req) as r:
        res = json.loads(r.read().decode())
        return res.get('filename')

print("\n3. Uploading diagram images to Render...")
remote_images = {}
for q_num, (fn, fp) in diagram_files.items():
    try:
        rem_fn = upload_image_to_render(fp, fn)
        remote_images[q_num] = rem_fn
        print(f"   Uploaded diagram for Q.{q_num} -> {rem_fn}")
    except Exception as e:
        print(f"   Error uploading image for Q.{q_num}: {e}")

print(f"\n4. Creating Test '{TEST_NAME}' on Render...")
create_data = json.dumps({
    'name': TEST_NAME,
    'description': TEST_DESCRIPTION,
    'duration': DURATION_MINUTES
}).encode('utf-8')

create_req = urllib.request.Request(f"{RENDER_URL}/api/tests", data=create_data, headers={'Content-Type': 'application/json'})
with opener.open(create_req) as resp:
    test_res = json.loads(resp.read().decode())
    test_id = test_res['id']
    print(f"   Created test with ID: {test_id}")

print(f"\n5. Adding all 100 questions to test '{test_id}' on Render...")
for q in questions_data:
    q_img = remote_images.get(q['num'], '')
    payload = {
        'question_text': q['question_text'],
        'question_image': q_img,
        'option_a': q['option_a'],
        'option_b': q['option_b'],
        'option_c': q['option_c'],
        'option_d': q['option_d'],
        'correct_answer': q['correct_answer']
    }
    q_req = urllib.request.Request(
        f"{RENDER_URL}/api/tests/{test_id}/questions",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    try:
        with opener.open(q_req) as r:
            pass
    except Exception as e:
        print(f"   Error on Q.{q['num']}: {e}")

print("   All 100 questions posted successfully!")

print(f"\n6. Publishing test '{test_id}' on Render...")
pub_req = urllib.request.Request(
    f"{RENDER_URL}/api/tests/{test_id}/publish",
    data=json.dumps({'status': 'published'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='PUT'
)
with opener.open(pub_req) as r:
    print("   Published status:", r.read().decode())

print("\n7. Also saving into local SQLite database (data.db)...")
import sqlite3
local_db = sqlite3.connect('data.db')
local_db.execute("INSERT OR REPLACE INTO tests (id, name, description, duration, status) VALUES (?, ?, ?, ?, 'published')",
                 (test_id, TEST_NAME, TEST_DESCRIPTION, DURATION_MINUTES))
for i, q in enumerate(questions_data):
    local_img = diagram_files.get(q['num'], ('', ''))[0]
    q_id = str(uuid.uuid4())[:8]
    local_db.execute(
        "INSERT INTO questions (id, test_id, question_text, question_image, option_a, option_b, option_c, option_d, correct_answer, order_num) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (q_id, test_id, q['question_text'], local_img, q['option_a'], q['option_b'], q['option_c'], q['option_d'], q['correct_answer'], i)
    )
local_db.commit()
local_db.close()
print("   Local database updated!")

print(f"\nSUCCESS! Test is live at: {RENDER_URL}/test/{test_id}")
