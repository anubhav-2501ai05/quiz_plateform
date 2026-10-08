import fitz
import re
import os
import json
import uuid
import ssl
import http.cookiejar
import urllib.request
import sqlite3
import sys

sys.stdout.reconfigure(line_buffering=True)

PDF_PATH = r"C:\Users\kumar\.gemini\antigravity-ide\brain\1b15ad05-f39b-4990-9d1c-8405be74c35d\.user_uploaded\media_1791468636889.pdf"
RENDER_URL = "https://quiz-plateform.onrender.com"
ADMIN_PASSWORD = "admin123"
TEST_NAME = "Full Length 8"
TEST_DESCRIPTION = "RRB JE CBT-1 (18 dec 2024 shift 2) - 100 Questions"
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

# Extract images using exact text bounds
table_images = {}
rects = {
    36: (6, fitz.Rect(25, 450, 450, 685))
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

# Handle special cases where text extraction failed or needs override
special_questions = {
    9: {
        'text': "Washing soda is represented by Na₂CO₃.xH₂O. The value of 'x' is equal to:"
    },
    18: {
        'text': "Find the value of 2.38̄ ÷ 0.54̄.",
        'A': "4 19/49", 'B': "3 17/21", 'C': "5 26/51", 'D': "6 29/57"
    },
    22: {
        'text': "Find the value of sin²63° + sin²27° + cos²17° + cos²73° + cos²90°."
    },
    33: {
        'text': "(a⁴ x b³ x c⁴) / (a⁹ x b⁴ x c⁸) in simplified form is:",
        'A': "(a⁷) x (b⁹) x (c⁸)", 'B': "(a⁻⁹) x (b⁻²) x (c⁻²)", 'C': "(a⁷) x (b⁸) x (c⁻⁹)", 'D': "(a⁻⁵) x (b⁻¹) x (c⁻⁴)"
    },
    36: {
        'text': ''
    },
    49: {
        'text': "When sodium carbonate (Na₂CO₃) is dissolved in water, the resulting solution becomes:"
    },
    58: {
        'A': "ΔPQR ≅ ΔYXZ", 'B': "ΔPQR ≅ ΔXYZ", 'C': "ΔQPR ≅ ΔXYZ", 'D': "ΔPRQ ≅ ΔXYZ"
    },
    61: {
        'text': "In a test, Chris has to answer two questions. The probability that he will answer the first question correctly is 1/5. If he answers the first question correctly, the probability that he will answer the second question correctly is 5/6. If Chris does not answer the first question correctly, the probability that he will answer the second question correctly is 1/4. Find the probability that Chris will answer the second question INCORRECTLY.\n[Note: Assume that each question will be answered — either correctly or incorrectly.]",
        'A': "19/30", 'B': "3/5", 'C': "2/3", 'D': "7/10"
    },
    62: {
        'A': "(3, 0)", 'B': "(-7, 0)", 'C': "(-7/3, 0)", 'D': "(-1/4, 0)"
    },
    64: {
        'text': "What is the resistivity (ρ) of a material?"
    },
    66: {
        'A': "56%", 'B': "63%", 'C': "60%", 'D': "61%"
    },
    67: {
        'text': "Solve the following linear equation.\n2x - y + z = 8, x + y - z = 10, x + y + 2z = 12",
        'A': "x = -1/3, y = 6, z = 14/3", 'B': "x = -6, y = -14/3, z = 1/3", 'C': "x = 2/3, y = -6, z = 14/3", 'D': "x = 6, y = 14/3, z = 2/3"
    },
    87: {
        'text': "If 546 apples were distributed among Neeraj, Vidya, and Mohan in the ratio 1/6 : 1/2 : 1/3, how many apples did the Mohan get?"
    },
    96: {
        'text': "In ΔABC, DE || AC, where D and E are the points on sides AB and BC, respectively.\nIf BD = 8 cm and AD = 7 cm, then what is the ratio of the area of ΔBDE to the trapezium ADEC?",
        'A': "161:64", 'B': "65:162", 'C': "64:161", 'D': "162:65"
    },
    99: {
        'text': "The total surface area of a solid hemisphere is 191 cm². Its radius (in cm) is:\n(Take π = 22/7)",
        'A': "√(1347 / 66)", 'B': "√(1347 / 132)", 'C': "√(1337 / 66)", 'D': "√(1345 / 66)"
    },
    100: {
        'D': "Leaves"
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

# 2. Save to local SQLite database
print("\n2. Saving to local database (data.db)...")
test_id = str(uuid.uuid4())[:8]
conn = sqlite3.connect('data.db')
conn.execute("INSERT INTO tests (id, name, description, duration, status) VALUES (?, ?, ?, ?, 'published')",
             (test_id, TEST_NAME, TEST_DESCRIPTION, DURATION_MINUTES))

for i, q in enumerate(questions_data):
    q_id = str(uuid.uuid4())[:8]
    local_img = q['image'][0] if q['image'] else ''
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
for attempt in range(3):
    try:
        with opener.open(login_req, timeout=15) as resp:
            print("   Login status:", resp.read().decode())
        break
    except Exception as e:
        if attempt == 2: raise e
        import time
        time.sleep(2)

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
    with opener.open(req, timeout=15) as r:
        res = json.loads(r.read().decode())
        return res.get('filename')

remote_images = {}
for q_num, (fn, fp) in table_images.items():
    for attempt in range(3):
        try:
            rem_fn = upload_img(fp, fn)
            remote_images[q_num] = rem_fn
            print(f"   Uploaded image for Q.{q_num} -> {rem_fn}")
            break
        except Exception as e:
            if attempt == 2:
                print(f"   Error uploading image for Q.{q_num}: {e}")
            import time
            time.sleep(2)

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
import time

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
        f"{RENDER_URL}/api/tests/{render_test_id}/questions",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with opener.open(q_req, timeout=15) as r:
                print(f"\r   Uploaded Q.{q['num']}/100", end="")
            break
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"\n   Failed to upload Q.{q['num']}: {e}")
                exit(1)
            time.sleep(2)

print("   All 100 questions uploaded!")

print("\n6. Publishing test on Render...")
pub_req = urllib.request.Request(
    f"{RENDER_URL}/api/tests/{render_test_id}/publish",
    data=json.dumps({'status': 'published'}).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='PUT'
)
with opener.open(pub_req) as r:
    print(f"   Published status: {r.read().decode()}")

print(f"\nSUCCESS! Test live at: {RENDER_URL}/test/{render_test_id}")
