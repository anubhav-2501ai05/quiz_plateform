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
    for line_id, line in enumerate(lines):
        line['spans'].sort(key=lambda s: s['bbox'][0])
        for s in line['spans']:
            s['line_id'] = line_id
            ordered_spans.append(s)
    return ordered_spans

print("1. Parsing questions from PDF...")
doc = fitz.open(PDF_PATH)
os.makedirs('uploads', exist_ok=True)

# Extract images for Q.2 (page 1) and Q.17 (page 4) using hardcoded rects
table_images = {}
rects = {
    2: (0, fitz.Rect(25, 445, 560, 508)),
    17: (3, fitz.Rect(25, 615, 450, 682))
}
mat = fitz.Matrix(4, 4)
for q_num, (p_idx, rect) in rects.items():
    try:
        page = doc[p_idx]
        padded_rect = rect + (-2, -2, 2, 2)
        pix = page.get_pixmap(matrix=mat, clip=padded_rect)
        if pix.n >= 5:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        fn = f"q_{q_num}_{uuid.uuid4().hex[:6]}.png"
        fp = os.path.join('uploads', fn)
        pix.save(fp)
        table_images[q_num] = (fn, fp)
        print(f"   Extracted image for Q.{q_num}: {fn}")
    except Exception as e:
        print(f"   Failed to extract image for Q.{q_num}: {e}")

questions_data = []

# Special manual overrides for math formula images and subscripts
special_questions = {
    6: {
        'text': "A number when increased by 50%, gives 2760. The number is:"
    },
    7: {
        'text': "Write the expanded form of (5a + 6b + 8c)².",
        'A': "25a² + 36b² + 64c² + 64ab + 96bc + 80ac",
        'B': "25a² + 36b² + 64c² + 60ab + 91bc + 80ac",
        'C': "25a² + 36b² + 64c² + 60ab + 96bc + 80ac",
        'D': "25a² + 36b² + 64c² + 60ab + 96bc + 90ac"
    },
    11: {
        'text': "20 ml of NaOH is neutralised by 10 ml of HNO₃. How much NaOH will be required to neutralise 15 ml of HNO₃?"
    },
    13: {
        'text': "The volume (in cm³) of a wire of diameter 56 cm and length 3 m is: (take π = 22/7)"
    },
    14: {
        'text': "Which of the following was the venue of the 46th session of the UNESCO World Heritage Committee?"
    },
    45: {
        'text': "Which of the following statements is INCORRECT?",
        'A': "Sonia Gandhi became the Leader of Opposition in the 18th Lok Sabha.",
        'B': "Narendra Modi took oath as the Prime Minister of India in June 2024.",
        'C': "Om Birla is elected as the Speaker of the 18th Lok Sabha.",
        'D': "Amit Shah assumed charge as Union Home Minister and Minister of Cooperation in June 2024."
    },
    47: {
        'text': "Write the expanded form of (6a + 8b + 3c)².",
        'A': "36a² + 64b² + 9c² + 96ab + 43bc + 36ac",
        'B': "36a² + 64b² + 9c² + 100ab + 48bc + 36ac",
        'C': "36a² + 64b² + 9c² + 96ab + 48bc + 46ac",
        'D': "36a² + 64b² + 9c² + 96ab + 48bc + 36ac"
    },
    50: {
        'text': "The balanced equation which shows the decomposition of hydrogen peroxide is:",
        'A': "2HO₂ → 2HO + O₂",
        'B': "H₂O₂ → 2H₂O + O₂",
        'C': "H₂O₂ → H₂O + O₂",
        'D': "2H₂O₂ → 2H₂O + O₂"
    },
    54: {
        'text': "Write the expanded form of (7a + 9b + 4c)².",
        'A': "49a² + 81b² + 16c² + 126ab + 72bc + 56ac",
        'B': "49a² + 81b² + 16c² + 126ab + 72bc + 66ac",
        'C': "49a² + 81b² + 16c² + 130ab + 72bc + 56ac",
        'D': "49a² + 81b² + 16c² + 126ab + 67bc + 56ac"
    },
    72: {
        'text': "If the area of a trapezium is 80 cm² and the parallel sides are 13.5 and 6.5 cm, then the distance between them (in cm) is ______."
    },
    75: {
        'text': "In a row of 38 students facing north, Sunil is 20th from the left end. If Harsh is 10th to the right of Sunil, what is Harsh's position from the right end of the row?",
        'A': "6th",
        'B': "7th",
        'C': "8th",
        'D': "9th"
    },
    83: {
        'text': "Which of the following received the top honour in the Best Urban Local Body category at the 5th National Water Awards for its innovative water conservation initiatives?"
    },
    86: {
        'text': "In the reaction: Zn + CuSO₄ → ZnSO₄ + Cu, what happens to zinc?"
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
        
        q_text = ""
        in_options = False
        opt_a, opt_b, opt_c, opt_d = "", "", "", ""
        curr_opt = None
        correct_opt = None
        last_q_line = -1
        last_o_line = -1
        
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
                    if curr_opt == 1: opt_a += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + opt_content if opt_a else opt_content
                    elif curr_opt == 2: opt_b += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + opt_content if opt_b else opt_content
                    elif curr_opt == 3: opt_c += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + opt_content if opt_c else opt_content
                    elif curr_opt == 4: opt_d += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + opt_content if opt_d else opt_content
                    if is_green(s['color']):
                        correct_opt = curr_opt
                else:
                    if curr_opt:
                        if curr_opt == 1: opt_a += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + t if opt_a else t
                        elif curr_opt == 2: opt_b += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + t if opt_b else t
                        elif curr_opt == 3: opt_c += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + t if opt_c else t
                        elif curr_opt == 4: opt_d += ('\n' if last_o_line != -1 and s['line_id'] != last_o_line else ' ') + t if opt_d else t
                        if is_green(s['color']):
                            correct_opt = curr_opt
                last_o_line = s['line_id']
            else:
                if q_text:
                    if last_q_line != -1 and s['line_id'] != last_q_line:
                        q_text += '\n'
                    elif not q_text.endswith('\n') and not q_text.endswith(' '):
                        q_text += ' '
                q_text += t
                last_q_line = s['line_id']
                
        q_text = q_text.strip()
        opt_a = opt_a.strip()
        opt_b = opt_b.strip()
        opt_c = opt_c.strip()
        opt_d = opt_d.strip()
        
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
            'image': table_images.get(q_num)
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

# 2. Update local SQLite database inplace
print("\n2. Updating local database (data.db)...")
conn = sqlite3.connect('data.db')
conn.row_factory = sqlite3.Row
latest_test = conn.execute("SELECT * FROM tests WHERE name='Full Length 4' ORDER BY created_at DESC LIMIT 1").fetchone()
if not latest_test:
    print("Test not found locally!")
    exit(1)
test_id = latest_test['id']
local_questions = conn.execute("SELECT * FROM questions WHERE test_id=? ORDER BY order_num ASC", (test_id,)).fetchall()

for i, q in enumerate(questions_data):
    q_id = local_questions[i]['id']
    local_img = q['image'][0] if q['image'] else local_questions[i]['question_image']
    conn.execute(
        "UPDATE questions SET question_text=?, option_a=?, option_b=?, option_c=?, option_d=?, question_image=? WHERE id=?",
        (q['question_text'], q['option_a'], q['option_b'], q['option_c'], q['option_d'], local_img, q_id)
    )
conn.commit()
conn.close()
print(f"   Updated local data.db for ID: {test_id}")

# 3. Upload to Render
print(f"\n3. Authenticating with Render ({RENDER_URL})...")
ctx = ssl.create_default_context()
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), urllib.request.HTTPSHandler(context=ctx))

login_data = json.dumps({'password': ADMIN_PASSWORD}).encode('utf-8')
login_req = urllib.request.Request(f"{RENDER_URL}/api/auth/login", data=login_data, headers={'Content-Type': 'application/json'})
with opener.open(login_req) as resp:
    print("   Login status:", resp.read().decode())

def upload_img(local_fp, fn):
    boundary = '----FormBoundary' + uuid.uuid4().hex
    with open(local_fp, 'rb') as f:
        file_bytes = f.read()
    header = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"image\"; filename=\"{fn}\"\r\n"
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

remote_images = {}
for q_num, (fn, fp) in table_images.items():
    try:
        rem_fn = upload_img(fp, fn)
        remote_images[q_num] = rem_fn
        print(f"   Uploaded image for Q.{q_num} -> {rem_fn}")
    except Exception as e:
        print(f"   Error uploading image for Q.{q_num}: {e}")

print(f"\n4. Fetching Test '{TEST_NAME}' from Render...")
req = urllib.request.Request(f"{RENDER_URL}/api/tests")
with opener.open(req) as r:
    remote_tests = json.loads(r.read().decode())
remote_test = next((t for t in remote_tests if t['name'] == 'Full Length 4'), None)
if not remote_test:
    print("Remote test not found!")
    exit(1)
render_test_id = remote_test['id']
print(f"   Found remote test ID: {render_test_id}")

req = urllib.request.Request(f"{RENDER_URL}/api/tests/{render_test_id}/questions")
with opener.open(req) as r:
    remote_questions = json.loads(r.read().decode())
remote_questions.sort(key=lambda x: x.get('order_num', 0))

print(f"\n5. Updating all 100 questions on Render (Inplace)...")
for i, q in enumerate(questions_data):
    rq_id = remote_questions[i]['id']
    # keep existing remote image (f9410b...) unless we uploaded a new one via script
    q_img = remote_images.get(q['num'])
    if not q_img:
        q_img = remote_questions[i]['question_image']
    
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
        f"{RENDER_URL}/api/tests/{render_test_id}/questions/{rq_id}",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT'
    )
    with opener.open(q_req) as r:
        pass

print("   All 100 questions updated!")
print(f"\n\nSUCCESS! Test updated inplace at: {RENDER_URL}/test/{render_test_id}")

print(f"\nSUCCESS! Test live at: {RENDER_URL}/test/{render_test_id}")
