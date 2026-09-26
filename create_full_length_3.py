import fitz
import re
import os
import json
import uuid
import ssl
import http.cookiejar
import urllib.request
import sqlite3

PDF_PATH = r"C:\Users\kumar\Downloads\16-December-2024-Shift-3-English.pdf"
RENDER_URL = "https://quiz-plateform.onrender.com"
ADMIN_PASSWORD = "admin123"
TEST_NAME = "Full Length 3"
TEST_DESCRIPTION = "RRB JE CBT-1 (16-December-2024 Shift 3) - 100 Questions"
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

# Extract images for Q.43 (table) and Q.76 (Venn diagram)
diagram_images = {}
for q_num, xref in [(43, 132), (76, 197)]:
    try:
        pix = fitz.Pixmap(doc, xref)
        if pix.n >= 5:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        fn = f"q_{q_num}_{uuid.uuid4().hex[:6]}.png"
        fp = os.path.join('uploads', fn)
        pix.save(fp)
        diagram_images[q_num] = (fn, fp)
        print(f"   Extracted image for Q.{q_num}: {fn}")
    except Exception as e:
        print(f"   Failed to extract image for Q.{q_num}: {e}")

# Special overrides for math equations / tables with clean multi-line formatting
special_overrides = {
    6: {
        'text': "If x varies inversely as y³ − 1 and is equal to 7 when y = 2, find x when y = 6.",
        'A': "49/215",
        'B': "49/216",
        'C': "50/216",
        'D': "51/215",
        'correct': "A"
    },
    7: {
        'text': (
            "A question is followed by two statements numbered (I) and (II). You have to decide whether the data provided in the statements are sufficient to answer the question. Read both the statements and select the most appropriate answer.\n\n"
            "Question:\n"
            "Five friends, P, Q, R, S and T, are sitting around a circular table facing the centre. Who is sitting second to the left of T?\n\n"
            "Statements:\n"
            "(I) S sits second to the right of P. T sits to the immediate left of P.\n"
            "(II) Only one person sits between Q and R. P sits to the immediate left of R."
        )
    },
    18: {
        'text': "If the ratio of four angles of a quadrilateral is ∠A : ∠B : ∠C : ∠D :: 2 : 3 : 5 : 8, what is the value of ∠B?",
        'A': "60°",
        'B': "90°",
        'C': "50°",
        'D': "40°",
        'correct': "A"
    },
    25: {
        'text': "A cylindrical rod has an outer curved surface area of 4500 cm². If the length of the rod is 39 cm, then the outer radius (in cm) of the rod, correct to two places of decimal, is:\n(Take π = 22/7)"
    },
    34: {
        'text': (
            "Two sets of numbers are given below. In each set of numbers, certain mathematical operation(s) on the first number result(s) in the second number. Similarly, certain mathematical operation(s) on the second number result(s) in the third number and so on. Which of the given options follows the same set of operations as in the given sets?\n"
            "(NOTE: Operations should be performed on the whole numbers, without breaking down the numbers into their constituent digits. E.g. 13 – Operations on 13 such as adding / subtracting /multiplying to 13 can be performed. Breaking down 13 into 1 and 3 and then performing mathematical operations on 1 and 3 is not allowed.)\n\n"
            "6-36-46-92; 7-49-59-118"
        )
    },
    35: {
        'text': (
            "7 is related to 9.8 following a certain logic. Following the same logic, 11 is related to 15.4. To which of the given options is 9 related, following the same logic?\n\n"
            "(NOTE: Operations should be performed on the whole numbers, without breaking down the numbers into their constituent digits.)"
        )
    },
    36: {
        'text': "The selling price of 25 books is equal to the cost price of 41 books. Find the loss or gain percentage.",
        'A': "100/16 % gain",
        'B': "64% gain",
        'C': "100/16 % loss",
        'D': "64% loss",
        'correct': "B"
    },
    43: {
        'text': (
            "The mean marks of the following distribution is:\n\n"
            "Marks Obtained | No. of Students\n"
            "      83       |       9        \n"
            "      73       |       5        \n"
            "      20       |      18        \n"
            "      82       |      16        "
        ),
        'correct': "D"
    },
    44: {
        'text': (
            "What is the correct sequence of following mountain ranges of India from north to south?\n\n"
            "1. Vindhya Range\n"
            "2. Aravalli Range\n"
            "3. Ajanta Range\n"
            "4. Satpura Range"
        )
    },
    45: {
        'text': (
            "Refer to the following number and symbol series and answer the question that follows.\n"
            "Counting to be done from left to right only.\n\n"
            "(Left)  7 % > 9 2 & 4 < 3 # 8 $ 5 * 6 ^ # 1  (Right)\n\n"
            "If all the symbols are dropped from the series, which of the following will be third from the left?"
        )
    },
    47: {
        'text': (
            "What will come in the place of the question mark (?) in the following equation if ‘+’ and ‘−' are interchanged and ‘÷’ and ‘×’ are interchanged?\n\n"
            "51 − 8 ÷ 2 + 6 × 2 = ?"
        )
    },
    49: {
        'text': (
            "What should come in place of the question mark (?) in the given series based on the English alphabetical order?\n\n"
            "GNK   IPM   KRO   MTQ   ?"
        )
    },
    54: {
        'text': "Two pipes can fill a tank in 20 hours and 90 hours, respectively. The time (in hours) required to fill the tank when both pipes are opened simultaneously is:",
        'A': "179/9",
        'B': "183/8",
        'C': "177/13",
        'D': "180/11",
        'correct': "D"
    },
    57: {
        'text': (
            "Q, R, S, T, U and V live on six different floors of the same building.\n"
            "• The lowermost floor in the building is numbered 1, the floor above it, number 2 and so on till the topmost floor is numbered 6.\n"
            "• S lives on the third floor.\n"
            "• Only two people live between S and U.\n"
            "• R lives on one of the floors below U but immediately above Q.\n"
            "• Q does not live on the fourth floor.\n"
            "• V lives on an odd numbered floor.\n\n"
            "How many people live between T and Q?"
        )
    },
    63: {
        'text': "(a⁵ × b⁹ × c¹) / (a⁶ × b³ × c⁸) in simplified form is:",
        'A': "(a⁴) × (b⁻¹⁰) × (c¹)",
        'B': "(a⁻¹⁰) × (b⁻⁵) × (c⁻⁸)",
        'C': "(a⁻⁵) × (b³) × (c⁻⁶)",
        'D': "(a⁻¹) × (b⁶) × (c⁻⁷)",
        'correct': "D"
    },
    64: {
        'text': "If x is inversely proportional to y, and y = 7 when x = 5, find the value of x, when y = 90.",
        'A': "7/18",
        'B': "7/19",
        'C': "9/21",
        'D': "8/19",
        'correct': "A"
    },
    66: {
        'text': (
            "What should come in place of the question mark (?) in the given series?\n\n"
            "305   251   206   170   143   ?"
        )
    },
    68: {
        'text': (
            "Select the option in which the triads share the same relationship as that shared by the given triads.\n\n"
            "HAND - ANDH - NDHA\n"
            "BIRD - IRDB - RDBI"
        )
    },
    71: {
        'text': (
            "In a certain code language:\n"
            "• ‘fast and furious’ is coded as ‘bo li ke’\n"
            "• ‘quick is furious’ is coded as ‘ke ra ng’\n"
            "• ‘fast but quick’ is coded as ‘ng li ty’\n\n"
            "What is the code for 'furious' in that language?"
        )
    },
    72: {
        'text': (
            "Refer to the given number, symbol series and answer the question that follows.\n"
            "Counting to be done from left to right only.\n\n"
            "(Left)  2 3 $ 7 5 & 6 % 3 $ # 9 @ ) 7 + 6 ? > ? 4 7 5 $  (Right)\n\n"
            "How many such numbers are there each of which is immediately preceded by a symbol and also immediately followed by another symbol?"
        )
    },
    76: {
        'text': (
            "Study the given diagram carefully and answer the question that follows. The numbers in different sections indicate the number of persons/objects.\n\n"
            "How many such officers exist that are also scientists but not professors?"
        )
    },
    77: {
        'text': "Find the value of 2.5 × 4 + 3.68 ÷ 4 − 8.46 × 2 + 7.365 × 4 + 2.8 × 3 − 1.675 × 2."
    },
    82: {
        'text': (
            "S, T, U, V, W, X and Y are sitting around a circular table facing the centre.\n"
            "• S sits fourth to the left of W.\n"
            "• T sits second to the right of S.\n"
            "• V is neither the immediate neighbour of T nor S.\n"
            "• X sits third to the right of V.\n"
            "• Y is not the immediate neighbour of W.\n\n"
            "How many people are sitting between S and T, when counted from the left of S?"
        )
    },
    87: {
        'text': "Evaluate:\n\n16 + 18 ÷ 3 − 3 × 3"
    },
    88: {
        'text': (
            "In a certain code:\n"
            "• ‘floor door room’ is coded as ‘bn la mt’\n"
            "• ‘door chair table’ is coded as 'wd bn ka’\n"
            "• ‘chair room window’ is coded as ‘ka bz la’\n"
            "(All the codes are two-letter code only.)\n\n"
            "What is room coded as?"
        )
    },
    91: {
        'text': "If sin θ = 12/13, then what is the value of 26 sin θ − 10 sec θ?"
    },
    93: {
        'text': (
            "What should come in place of the question mark (?) in the given series?\n\n"
            "29   11   29   15   29   19   29   23   29   ?"
        )
    },
    94: {
        'text': (
            "Which of the following letter-clusters should replace # and % so that the pattern and relationship followed between the letter-cluster pair on the left side of :: is the same as that on the right side of ::?\n\n"
            "# : IBX :: HAW : %"
        )
    },
    97: {
        'text': (
            "Select the letter-cluster pair that best represents a similar relationship to the one expressed in the pairs of letter-clusters given below.\n\n"
            "DMO : HPM\n"
            "LIF : PLD"
        )
    },
    98: {
        'text': (
            "Which of the following statements is/are correct about the PM Vishwakarma Yojana?\n\n"
            "1) The PM Vishwakarma Yojana was launched by the Hon'ble Prime Minister on 17 September 2023.\n"
            "2) Scheme aims to provide end-to-end support to artisans and craftspeople who work with their hands and tools.\n"
            "3) The Scheme components include recognition through PM Vishwakarma Certificate and ID Card, Skill Upgradation, Toolkit Incentive, Credit Support, Incentive for Digital Transactions, and Marketing Support."
        )
    }
}

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
        
        # Apply special overrides
        if q_num in special_overrides:
            spec = special_overrides[q_num]
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
            'image': diagram_images.get(q_num)
        })

print(f"Parsed {len(questions_data)} questions.")

# Verify no issues
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
for q_num, (fn, fp) in diagram_images.items():
    try:
        rem_fn = upload_img(fp, fn)
        remote_images[q_num] = rem_fn
        print(f"   Uploaded image for Q.{q_num} -> {rem_fn}")
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
    render_test_id = test_res['id']
    print(f"   Created on Render with ID: {render_test_id}")

print(f"\n5. Uploading all 100 questions to Render...")
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
