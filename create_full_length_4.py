import fitz
import re
import os
import json
import uuid
import ssl
import http.cookiejar
import urllib.request
import sqlite3

PDF_PATH = r"C:\Users\kumar\Downloads\17-December-2024-Shift-1-English.pdf"
RENDER_URL = "https://quiz-plateform.onrender.com"
ADMIN_PASSWORD = "admin123"
TEST_NAME = "Full Length 4"
TEST_DESCRIPTION = "RRB JE CBT-1 (17-December-2024 Shift 1) - 100 Questions"
DURATION_MINUTES = 120  # 2 hours

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

print("1. Parsing questions from PDF...")
doc = fitz.open(PDF_PATH)
os.makedirs('uploads', exist_ok=True)

questions_data = []

# Special manual overrides for math formula images
special_questions = {
    7: {
        'text': "Write the expanded form of (5a + 6b + 8c)².",
        'A': "25a² + 36b² + 64c² + 64ab + 96bc + 80ac",
        'B': "25a² + 36b² + 64c² + 60ab + 91bc + 80ac",
        'C': "25a² + 36b² + 64c² + 60ab + 96bc + 80ac",
        'D': "25a² + 36b² + 64c² + 60ab + 96bc + 90ac"
    },
    13: {
        'text': "The volume (in cm³) of a wire of diameter 56 cm and length 3 m is: (take π = 22/7)"
    },
    17: {
        'text': "If 3x / (1 + 1 / (1 + x / (1 - x))) = 12, then find the value of 'x'."
    },
    47: {
        'text': "Write the expanded form of (6a + 8b + 3c)².",
        'A': "36a² + 64b² + 9c² + 96ab + 43bc + 36ac",
        'B': "36a² + 64b² + 9c² + 100ab + 48bc + 36ac",
        'C': "36a² + 64b² + 9c² + 96ab + 48bc + 46ac",
        'D': "36a² + 64b² + 9c² + 96ab + 48bc + 36ac"
    },
    54: {
        'text': "Write the expanded form of (7a + 9b + 4c)².",
        'A': "49a² + 81b² + 16c² + 126ab + 72bc + 56ac",
        'B': "49a² + 81b² + 16c² + 126ab + 72bc + 66ac",
        'C': "49a² + 81b² + 16c² + 130ab + 72bc + 56ac",
        'D': "49a² + 81b² + 16c² + 126ab + 67bc + 56ac"
    },
    99: {
        'text': "The diameters of two concentric circles are 34 cm and 50 cm. A straight line, CAPF, intersects the larger circle at points C and F and intersects the smaller circle at points A and P. If AP = 16 cm, find the length of CF."
    },
    100: {
        'B': "100/15 % gain",
        'D': "100/15 % loss"
    }
}

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
        
        # Apply special overrides
        if q_num in special_questions:
            spec = special_questions[q_num]
            if 'text' in spec:
                q_text = spec['text']
            if 'A' in spec:
                opt_a = spec['A']
            if 'B' in spec:
                opt_b = spec['B']
            if 'C' in spec:
                opt_c = spec['C']
            if 'D' in spec:
                opt_d = spec['D']
            if 'correct' in spec:
                correct_letter = spec['correct']
                
        questions_data.append({
            'num': q_num,
            'question_text': q_text,
            'option_a': opt_a,
            'option_b': opt_b,
            'option_c': opt_c,
            'option_d': opt_d,
            'correct_answer': correct_letter,
            'image': None
        })

print(f"Parsed {len(questions_data)} questions.")

# Verify no empty options or questions
for q in questions_data:
    if not q['question_text']:
        print(f"ERROR: Empty text for Q.{q['num']}")
    if not (q['option_a'] and q['option_b'] and q['option_c'] and q['option_d']):
        print(f"ERROR: Missing options for Q.{q['num']}")
    if not q['correct_answer']:
        print(f"ERROR: Missing answer for Q.{q['num']}")

# 2. Save to local SQLite database
print("\n2. Saving to local database (data.db)...")
test_id = str(uuid.uuid4())[:8]
conn = sqlite3.connect('data.db')
conn.execute("INSERT INTO tests (id, name, description, duration, status) VALUES (?, ?, ?, ?, 'published')",
             (test_id, TEST_NAME, TEST_DESCRIPTION, DURATION_MINUTES))

for i, q in enumerate(questions_data):
    q_id = str(uuid.uuid4())[:8]
    local_img = ''
    conn.execute(
        "INSERT INTO questions (id, test_id, question_text, question_image, option_a, option_b, option_c, option_d, correct_answer, order_num) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (q_id, test_id, q['question_text'], local_img, q['option_a'], q['option_b'], q['option_c'], q['option_d'], q['correct_answer'], i)
    )
conn.commit()
conn.close()
print(f"   Saved to local data.db with ID: {test_id}")

# 3. Upload to Render
print(f"\n3. Authenticating with Render ({RENDER_URL})...")
ctx = ssl.create_default_context()
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))

login_data = json.dumps({'password': ADMIN_PASSWORD}).encode('utf-8')
login_req = urllib.request.Request(f"{RENDER_URL}/api/auth/login", data=login_data, headers={'Content-Type': 'application/json'})
with opener.open(login_req) as resp:
    print("   Login status:", resp.read().decode())

print(f"\n4. Creating Test '{TEST_NAME}' on Render...")
create_data = json.dumps({
    'name': TEST_NAME,
    'description': TEST_DESCRIPTION,
    'duration': DURATION_MINUTES
}).encode('utf-8')

create_req = urllib.request.Request(f"{RENDER_URL}/api/tests", data=create_data, headers={'Content-Type': 'application/json'})
with opener.open(create_req) as resp:
    test_res = json.loads(resp.read().decode())
    render_test_id = test_res['id']
    print(f"   Created on Render with ID: {render_test_id}")

print(f"\n5. Uploading all 100 questions to Render...")
for q in questions_data:
    payload = {
        'question_text': q['question_text'],
        'question_image': '',
        'option_a': q['option_a'],
        'option_b': q['option_b'],
        'option_c': q['option_c'],
        'option_d': q['option_d'],
        'correct_answer': q['correct_answer']
    }
    q_req = urllib.request.Request(
        f"{RENDER_URL}/api/tests/{render_test_id}/questions",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with opener.open(q_req) as r:
        pass

print("   All 100 questions uploaded!")

print("\n6. Publishing test on Render...")
pub_req = urllib.request.Request(
    f"{RENDER_URL}/api/tests/{render_test_id}/publish",
    data=json.dumps({'status': 'published'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='PUT'
)
with opener.open(pub_req) as r:
    print("   Published status:", r.read().decode())

print(f"\nSUCCESS! Test live at: {RENDER_URL}/test/{render_test_id}")
