import urllib.request
import json
import sqlite3

RENDER_URL = "https://quiz-plateform.onrender.com"
ADMIN_PASSWORD = "admin123"
TEST_NAME = "Full Length 5"

# The fixes for the questions
fixes = {
    58: {
        'option_a': "NaHCO₃",
        'option_b': "Na₂CO₃·10H₂O",
        'option_c': "NaCl",
        'option_d': "Na₂CO₃"
    },
    61: {
        'question_text': "The radius of the base of a right circular cone is 21 m and its curved surface area is 1914 m². Find the volume (in m³) of the cone."
    },
    79: {
        'option_a': "C₂H₄, C₂H₆, C₃H₆, C₄H₈",
        'option_b': "C₂H₂, C₂H₄, C₃H₆, C₄H₈",
        'option_c': "CH₄, C₂H₆, C₃H₈, C₄H₁₀",
        'option_d': "C₃H₇OH, C₄H₉OH, C₅H₁₁OH, C₆H₁₁OH"
    },
    82: {
        'question_text': "Simplify the given expression.\n(sin A + cosec A)² + (cos A - sec A)² + 3",
        'option_a': "1 + tan²A + cot²A",
        'option_b': "tan²A + cot²A",
        'option_c': "3 + tan²A + cot²A",
        'option_d': "6 + tan²A + cot²A"
    },
    85: {
        'option_a': "2.26 × 10⁸ m/s",
        'option_b': "1.5 × 10⁸ m/s",
        'option_c': "4 × 10⁸ m/s",
        'option_d': "3 × 10⁸ m/s"
    }
}

print("1. Authenticating with Render...")
login_data = json.dumps({'password': ADMIN_PASSWORD}).encode('utf-8')
req = urllib.request.Request(f"{RENDER_URL}/api/auth/login", data=login_data, headers={'Content-Type': 'application/json'})
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
with opener.open(req) as resp:
    print(f"   Login status: {resp.read().decode()}")

print(f"\n2. Fetching Test '{TEST_NAME}' from Render...")
req = urllib.request.Request(f"{RENDER_URL}/api/tests")
with opener.open(req) as r:
    remote_tests = json.loads(r.read().decode())

remote_test = next((t for t in remote_tests if t['name'] == TEST_NAME), None)
if not remote_test:
    print("Remote test not found!")
    exit(1)
render_test_id = remote_test['id']
print(f"   Found remote test ID: {render_test_id}")

req = urllib.request.Request(f"{RENDER_URL}/api/tests/{render_test_id}/questions")
with opener.open(req) as r:
    remote_questions = json.loads(r.read().decode())

# Sort questions by order_num so Q.58 is index 57, etc.
remote_questions.sort(key=lambda x: x.get('order_num', 0))

print("\n3. Updating specific questions inplace on Render...")
for q_num, data in fixes.items():
    idx = q_num - 1
    if idx < 0 or idx >= len(remote_questions):
        print(f"   Invalid Q index: {idx}")
        continue
    
    rq = remote_questions[idx]
    rq_id = rq['id']
    
    payload = {
        'question_text': data.get('question_text', rq['question_text']),
        'question_image': rq['question_image'],
        'option_a': data.get('option_a', rq['option_a']),
        'option_b': data.get('option_b', rq['option_b']),
        'option_c': data.get('option_c', rq['option_c']),
        'option_d': data.get('option_d', rq['option_d']),
        'correct_answer': rq.get('correct_answer', 'A') # Fallback if admin check fails
    }
    
    # We must preserve the correct_answer. Since we're an admin, GET questions might not return correct_answer if session is lost?
    # Wait, GET /questions as admin returns correct_answer.
    if 'correct_answer' not in rq:
        print("   WARNING: correct_answer not found in GET response, skipping update to prevent data loss!")
        continue

    payload['correct_answer'] = rq['correct_answer']

    q_req = urllib.request.Request(
        f"{RENDER_URL}/api/tests/{render_test_id}/questions/{rq_id}",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT'
    )
    with opener.open(q_req) as r:
        pass
    print(f"   Updated Q.{q_num} successfully!")

print("\n4. Updating local SQLite database...")
conn = sqlite3.connect('data.db')
local_test = conn.execute("SELECT id FROM tests WHERE name=?", (TEST_NAME,)).fetchone()
if local_test:
    local_test_id = local_test[0]
    local_qs = conn.execute("SELECT id, order_num FROM questions WHERE test_id=? ORDER BY order_num ASC", (local_test_id,)).fetchall()
    
    for q_num, data in fixes.items():
        idx = q_num - 1
        if idx < len(local_qs):
            lq_id = local_qs[idx][0]
            sets = []
            vals = []
            for k, v in data.items():
                sets.append(f"{k}=?")
                vals.append(v)
            if sets:
                vals.append(lq_id)
                query = f"UPDATE questions SET {', '.join(sets)} WHERE id=?"
                conn.execute(query, tuple(vals))
    conn.commit()
    print("   Local database updated successfully!")
conn.close()

print("\nDONE!")
