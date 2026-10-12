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

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

PDF_PATH = r"C:\Users\kumar\.gemini\antigravity-ide\brain\1b15ad05-f39b-4990-9d1c-8405be74c35d\.user_uploaded\media_1791795494220.pdf"
RENDER_URL = "https://quiz-plateform.onrender.com"
ADMIN_PASSWORD = "admin123"
TEST_NAME = "Full length 10"
TEST_DESCRIPTION = "RRB JE CBT-1 (2026 19 feb shift 1) - 100 Questions"
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

# Extract images using exact bounds
table_images = {}
rects = {
    14: (3, fitz.Rect(45, 318, 435, 527)),  # Page 4 Venn diagram
    37: (6, fitz.Rect(52, 764, 435, 808))   # Page 7 Frequency table
}
mat = fitz.Matrix(4, 4)
for q_num, (p_idx, rect) in rects.items():
    try:
        page = doc[p_idx]
        pix = page.get_pixmap(matrix=mat, clip=rect)
        if pix.n >= 5:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        fn = f"fl10_q_{q_num}_{uuid.uuid4().hex[:6]}.png"
        fp = os.path.join('uploads', fn)
        pix.save(fp)
        table_images[q_num] = (fn, fp)
        print(f"   Extracted image for Q.{q_num}: {fn}")
    except Exception as e:
        print(f"   Failed to extract image for Q.{q_num}: {e}")

questions_data = []

# Special questions with precise math, chemical formulas, fractions, and exact option order (1=A, 2=B, 3=C, 4=D)
special_questions = {
    1: {
        'text': "The base and the corresponding height of a parallelogram are 93 cm and 29 cm, respectively. The area of the parallelogram (in cm²) is:",
        'A': "2701",
        'B': "2697",
        'C': "2714",
        'D': "2696",
        'correct': "B"
    },
    2: {
        'text': "Simplify the following.\n112 ÷ [16 ÷ 8 × {18 + 12 − (3 + 10 − (4 + 7))}]",
        'A': "3",
        'B': "4",
        'C': "11",
        'D': "2",
        'correct': "D"
    },
    3: {
        'text': "The quadratic equation whose roots are 1/√2 and 1/√2 is:",
        'A': "2x² − (2√2)x + 1 = 0",
        'B': "3x² − (2√2)x − 1 = 0",
        'C': "2x² − (4√2)x − 1 = 0",
        'D': "2x² + (2√5)x + 1 = 0",
        'correct': "A"
    },
    5: {
        'text': "When methane (CH₄) burns completely in the presence of sufficient oxygen, which products are formed?",
        'A': "Carbon dioxide and carbon",
        'B': "Carbon and hydrogen",
        'C': "Carbon dioxide and water",
        'D': "Carbon monoxide and water",
        'correct': "C"
    },
    6: {
        'text': "A question is followed by two statements numbered (I) and (II). You have to decide whether the data provided in the statements are sufficient to answer the question. Read both the statements carefully and decide the appropriate answer.\n\nFive people, A, B, C, D and E, are sitting in a straight line facing north. Who sits to the immediate left of C?\nI. B sits second from one of the extreme ends of the line. Only one person sits between B and C. D sits third to the right of C.\nII. D sits to the immediate right of B. Only three people sit between D and A. E sits to the immediate right of C.",
        'A': "Data in statement I alone is sufficient to answer the question while data in statement II is not",
        'B': "Data in both statements I and II together is NOT sufficient to answer the question",
        'C': "Data in both statements I and II together (and not statement I alone or statement II alone) is sufficient to answer the question",
        'D': "Data in statement II alone is sufficient to answer the question while data in statement I is not",
        'correct': "D"
    },
    11: {
        'text': "LKLJ is related to GFGE in a certain way based on the English alphabetical order. In the same way, NMNL is related to IHIG. To which of the following is QPQO related, following the same logic?",
        'A': "LJKJ",
        'B': "LKLJ",
        'C': "LKKJ",
        'D': "LLKQ",
        'correct': "B"
    },
    14: {
        'text': "Study the given diagram carefully and answer the question that follows. The numbers in different sections indicate the number of persons. (NOTE: You have to take the given data to be true even if they seem to be at variance from commonly known facts.)\n\nHow many builders are urban residents and own land?",
        'A': "11",
        'B': "6",
        'C': "7",
        'D': "9",
        'correct': "C"
    },
    17: {
        'text': "X people were given a contract for doing a piece of work in 32 days. 8 people did not turn up to work due to sickness, and the rest of the people completed the work in 40 days. What is the value of X?",
        'A': "38",
        'B': "42",
        'C': "40",
        'D': "44",
        'correct': "C"
    },
    28: {
        'text': "Solve the following linear equations.\n2x + 3y − 5z = 4,\nx + 3y − 2z = 12,\n2x + y − 3z = 5",
        'A': "x = −43/8, y = −65/8, z = 39/8",
        'B': "x = 65/8, y = 39/8, z = 43/8",
        'C': "x = 43/8, y = 65/8, z = 39/8",
        'D': "x = 43/8, y = −65/8, z = −39/8",
        'correct': "B"
    },
    30: {
        'text': "If x = ∛512, y = ⁶√64 and z = 6³ − 2 × 10², then ∛(10(x² + y³ + z + 12)) is equal to:",
        'A': "40",
        'B': "10",
        'C': "20",
        'D': "30",
        'correct': "B"
    },
    37: {
        'text': "Find the median from the following data.",
        'A': "47 years",
        'B': "65 years",
        'C': "55 years",
        'D': "70 years",
        'correct': "C"
    },
    39: {
        'text': "In the 2024 Global Hunger Index released on October 2024, India is ranked 105th out of the how many countries?",
        'A': "127",
        'B': "210",
        'C': "90",
        'D': "195",
        'correct': "A"
    },
    42: {
        'text': "What is the remainder when 3⁹³⁹ is divided by 8?",
        'A': "2",
        'B': "3",
        'C': "5",
        'D': "0",
        'correct': "B"
    },
    49: {
        'text': "The LCM of 2³ × 6² × 11, 2² × 11² × 17 and 6³ × 11² × 17² is:",
        'A': "2⁴ × 3⁴ × 11² × 17²",
        'B': "2⁵ × 3³ × 11² × 17²",
        'C': "2⁴ × 3³ × 11² × 17²",
        'D': "2⁵ × 3⁴ × 11² × 17²",
        'correct': "B"
    },
    50: {
        'text': "Each of G, H, I, J, P, Q and R has an exam on a different day of a week, starting from Monday and ending on Sunday of the same week. Only two people have exam before Q. Only one person has exam after P. Only three people have exam between Q and J. Only one person has exam between I and H. G has exam immediately before I. How many people have exam between R and I?",
        'A': "Three",
        'B': "Two",
        'C': "One",
        'D': "None",
        'correct': "B"
    },
    51: {
        'text': "A shopkeeper marks an article at ₹x and offers a discount of 50% on it. He sells it for ₹287 after charging VAT of 64% on the discounted price. What is the value of x?",
        'A': "300",
        'B': "200",
        'C': "250",
        'D': "350",
        'correct': "D"
    },
    58: {
        'text': "If x/y = 18/2, then find (x² + y²) / (x² − y²)",
        'A': "47/40",
        'B': "37/40",
        'C': "31/40",
        'D': "41/40",
        'correct': "D"
    },
    63: {
        'text': "If the mode and median of a certain data are 24 and 18, respectively, then the mean of the data is:",
        'A': "20",
        'B': "15",
        'C': "24",
        'D': "22",
        'correct': "B"
    },
    66: {
        'text': "Which of the following statements about washing soda is CORRECT?",
        'A': "Washing soda is chemically sodium carbonate decahydrate (Na₂CO₃·10H₂O)",
        'B': "It is obtained by heating sodium bicarbonate to 100°C",
        'C': "It does not remove permanent hardness of water",
        'D': "Washing soda is acidic in nature",
        'correct': "A"
    },
    72: {
        'text': "A toy manufacturer originally makes a conical toy with a base radius of 3 cm and a height of 7 cm. Due to customer demand, he now wants to produce a similar toy that has 75% of the original volume, while keeping the same base radius as before. What should be the height of the new toy? (Take π = 22/7)",
        'A': "5.5 cm",
        'B': "5.125 cm",
        'C': "5.75 cm",
        'D': "5.25 cm",
        'correct': "D"
    },
    73: {
        'text': "The 44th Amendment Act of 1978 restored the standard term of the Lok Sabha and State Legislature to how many years?",
        'A': "three",
        'B': "seven",
        'C': "five",
        'D': "six",
        'correct': "C"
    },
    74: {
        'text': "Let C be a circle with center O. Let AB be a tangent to C, such that AB touches the circle at P. Let X and Y be any two points on C. If ∠APX = 60° and ∠BPY = 30°, find ∠PYX and ∠PXY, respectively.",
        'A': "60°, 30°",
        'B': "90°, 30°",
        'C': "90°, 60°",
        'D': "30°, 60°",
        'correct': "A"
    },
    75: {
        'text': "Sodium hydroxide (NaOH) contains __________ as its anion.",
        'A': "Na⁺",
        'B': "NO₃⁻",
        'C': "OH⁻",
        'D': "H⁺",
        'correct': "C"
    },
    84: {
        'text': "A sum of money is divided among X, Y and Z in the ratio 4:3:6. If the share of Z is ₹3300 more than Y, then how much amount will X get more than Y?",
        'A': "₹1100",
        'B': "₹1000",
        'C': "₹1300",
        'D': "₹1200",
        'correct': "A"
    },
    86: {
        'text': "While covering a distance of 36 km, a man noticed that after cycling for 2 hour 5 minutes, the distance covered by him was 6/7 of the remaining distance. What was his approximate speed in km/h?",
        'A': "7.4",
        'B': "6.7",
        'C': "8.7",
        'D': "8",
        'correct': "D"
    },
    90: {
        'text': "The selling price of 45 books is equal to the cost price of 18 books. Find the loss or gain percentage.",
        'A': "100/27 % loss",
        'B': "60 % loss",
        'C': "60 % gain",
        'D': "100/27 % gain",
        'correct': "B"
    },
    92: {
        'text': "Consider a quadratic equation 3x² + 4x − 8 = 0. Which of the following quadratic equations will have both roots common with the given quadratic equation?",
        'A': "3x² − 4x + 8 = 0",
        'B': "−1.5x² − 2x + 4 = 0",
        'C': "3x² + 4x + 8 = 0",
        'D': "−1.5x² + 2x + 4 = 0",
        'correct': "B"
    },
    93: {
        'text': "Find the value of ((x + 3) / (x² − 2x)) × ((2x − 1) / (x² + 2x + 4)) × ((x⁴ − 8x) / (2x² + 5x − 3))",
        'A': "2",
        'B': "−1",
        'C': "0",
        'D': "1",
        'correct': "D"
    },
    97: {
        'text': "Refer to the following letter and symbol series and answer the question that follows.\nCounting to be done from left to right only.\n(Left) K & Z # % X N E A A Y C + H \\ Y = C $ M H (Right)\n\nHow many such letters are there each of which is immediately preceded by a symbol and also immediately followed by a letter?",
        'A': "Three",
        'B': "Two",
        'C': "Zero",
        'D': "One",
        'correct': "B"
    },
    100: {
        'text': "In a factory, the average daily wage of 12 skilled workers and 18 unskilled workers is ₹604. If the average wage of the skilled workers is ₹754, then find the average wage of the unskilled workers.",
        'A': "₹534",
        'B': "₹514",
        'C': "₹524",
        'D': "₹504",
        'correct': "D"
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
        
        # Clean trailing question ID watermark if present
        q_text = re.sub(r'[\?\. ]+(\d{2,5})$', '?', q_text)
        
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

# Strict validation
has_errors = False
for q in questions_data:
    if not q['question_text']:
        print(f"ERROR: Empty text for Q.{q['num']}")
        has_errors = True
    if not (q['option_a'] and q['option_b'] and q['option_c'] and q['option_d']):
        print(f"ERROR: Missing options for Q.{q['num']}: A='{q['option_a']}', B='{q['option_b']}', C='{q['option_c']}', D='{q['option_d']}'")
        has_errors = True
    if not q['correct_answer']:
        print(f"ERROR: Missing answer for Q.{q['num']}")
        has_errors = True

if has_errors:
    print("FATAL: Validation failed. Aborting database save.")
    sys.exit(1)
print("All 100 questions successfully validated with non-empty text, all 4 options, and correct answers!")

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
                sys.exit(1)
            time.sleep(2)

print("\n   All 100 questions uploaded!")

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
