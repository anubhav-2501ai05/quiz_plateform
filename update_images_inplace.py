import fitz
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

doc = fitz.open(PDF_PATH)
os.makedirs('uploads', exist_ok=True)

# 1. Extract high-res images
print("Extracting high-resolution images...")
table_images = {}
rects = {
    2: (0, fitz.Rect(58.4, 497.1, 555.5, 575.3)),
    17: (3, fitz.Rect(78.9, 638.1, 149.3, 706.8))
}
mat = fitz.Matrix(4, 4) # 4x scale for high resolution

for q_num, (p_idx, rect) in rects.items():
    page = doc[p_idx]
    padded_rect = rect + (-2, -2, 2, 2)
    pix = page.get_pixmap(matrix=mat, clip=padded_rect)
    
    if pix.n >= 5:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    
    fn = f"q_{q_num}_{uuid.uuid4().hex[:6]}_hires.png"
    fp = os.path.join('uploads', fn)
    pix.save(fp)
    table_images[q_num] = (fn, fp)
    print(f"   Extracted high-res image for Q.{q_num}: {fn}")

# 2. Get local DB info
print("\nLooking up latest test in local DB...")
conn = sqlite3.connect('data.db')
conn.row_factory = sqlite3.Row
latest_test = conn.execute("SELECT * FROM tests WHERE name='Full Length 4' ORDER BY created_at DESC LIMIT 1").fetchone()
if not latest_test:
    print("Test not found!")
    exit(1)

test_id = latest_test['id']
print(f"Found test: {latest_test['name']} (ID: {test_id})")

# We need the IDs for Q.2 (order_num=1) and Q.17 (order_num=16) since order_num is 0-indexed.
# Or better, let's fetch all questions and parse their text to find Q.2 and Q.17 exactly.
# Since the script inserted them in order, Q.2 is index 1, Q.17 is index 16.
questions = conn.execute("SELECT * FROM questions WHERE test_id=? ORDER BY order_num ASC", (test_id,)).fetchall()
q_2_id = questions[1]['id']
q_17_id = questions[16]['id']
print(f"Q.2 ID: {q_2_id}")
print(f"Q.17 ID: {q_17_id}")

# 3. Upload to Render
print(f"\nAuthenticating with Render...")
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
    print(f"Uploading image for Q.{q_num}...")
    rem_fn = upload_img(fp, fn)
    remote_images[q_num] = rem_fn
    print(f"   Uploaded -> {rem_fn}")

# 4. Update questions via API and local DB
update_mapping = {
    2: q_2_id,
    17: q_17_id
}

for q_num, q_id in update_mapping.items():
    rem_img = remote_images[q_num]
    
    # Update Render API
    payload = {'question_image': rem_img}
    req = urllib.request.Request(
        f"{RENDER_URL}/api/tests/{test_id}/questions/{q_id}",
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='PUT'
    )
    try:
        with opener.open(req) as r:
            print(f"Successfully updated Q.{q_num} on Render: {r.read().decode()}")
    except Exception as e:
        print(f"Failed to update Q.{q_num} on Render: {e}")
        
    # Update local DB
    conn.execute("UPDATE questions SET question_image=? WHERE id=? AND test_id=?", (rem_img, q_id, test_id))

conn.commit()
conn.close()
print("\nDone! Images have been replaced in-place locally and remotely.")
