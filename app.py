import os
import sqlite3
import uuid
import json
import hashlib
import secrets
import time
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, session, render_template

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Database ──────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS tests (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            duration INTEGER NOT NULL DEFAULT 30,
            status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            test_id TEXT NOT NULL,
            question_text TEXT DEFAULT '',
            question_image TEXT DEFAULT '',
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            order_num INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (test_id) REFERENCES tests(id) ON DELETE CASCADE
        );
    ''')
    conn.commit()
    conn.close()

init_db()


# ── Auth Helpers ──────────────────────────────────────────────────────

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ── Page Routes ───────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin')
@app.route('/admin/<path:subpath>')
def admin_page(subpath=''):
    return render_template('admin.html')


@app.route('/test/<test_id>')
@app.route('/test/<test_id>/<path:subpath>')
def test_page(test_id, subpath=''):
    return render_template('test.html')


# ── Auth API ──────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    password = data.get('password', '')
    if password == ADMIN_PASSWORD:
        session['is_admin'] = True
        return jsonify({'success': True})
    return jsonify({'error': 'Invalid password'}), 401


@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    return jsonify({'authenticated': bool(session.get('is_admin'))})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop('is_admin', None)
    return jsonify({'success': True})


# ── Tests API ─────────────────────────────────────────────────────────

@app.route('/api/tests', methods=['GET'])
def get_tests():
    conn = get_db()
    is_admin = session.get('is_admin')
    if is_admin:
        tests = conn.execute('SELECT * FROM tests ORDER BY created_at DESC').fetchall()
    else:
        tests = conn.execute("SELECT * FROM tests WHERE status='published' ORDER BY created_at DESC").fetchall()

    result = []
    for t in tests:
        count = conn.execute('SELECT COUNT(*) as c FROM questions WHERE test_id=?', (t['id'],)).fetchone()['c']
        result.append({**dict(t), 'question_count': count})
    conn.close()
    return jsonify(result)


@app.route('/api/tests', methods=['POST'])
@admin_required
def create_test():
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Test name is required'}), 400
    
    test_id = str(uuid.uuid4())[:8]
    description = data.get('description', '')
    duration = int(data.get('duration', 30))
    
    conn = get_db()
    conn.execute(
        'INSERT INTO tests (id, name, description, duration) VALUES (?, ?, ?, ?)',
        (test_id, name, description, duration)
    )
    conn.commit()
    conn.close()
    return jsonify({'id': test_id, 'name': name, 'description': description, 'duration': duration, 'status': 'draft'}), 201


@app.route('/api/tests/<test_id>', methods=['GET'])
def get_test(test_id):
    conn = get_db()
    test = conn.execute('SELECT * FROM tests WHERE id=?', (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({'error': 'Test not found'}), 404
    
    count = conn.execute('SELECT COUNT(*) as c FROM questions WHERE test_id=?', (test_id,)).fetchone()['c']
    conn.close()
    return jsonify({**dict(test), 'question_count': count})


@app.route('/api/tests/<test_id>', methods=['PUT'])
@admin_required
def update_test(test_id):
    data = request.get_json()
    conn = get_db()
    test = conn.execute('SELECT * FROM tests WHERE id=?', (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({'error': 'Test not found'}), 404
    
    name = data.get('name', test['name']).strip()
    description = data.get('description', test['description'])
    duration = int(data.get('duration', test['duration']))
    
    if not name:
        conn.close()
        return jsonify({'error': 'Test name is required'}), 400
    
    conn.execute(
        'UPDATE tests SET name=?, description=?, duration=?, updated_at=datetime("now") WHERE id=?',
        (name, description, duration, test_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/tests/<test_id>', methods=['DELETE'])
@admin_required
def delete_test(test_id):
    conn = get_db()
    # Delete associated question images
    questions = conn.execute('SELECT question_image FROM questions WHERE test_id=?', (test_id,)).fetchall()
    for q in questions:
        if q['question_image']:
            img_path = os.path.join(UPLOAD_DIR, q['question_image'])
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except OSError:
                    pass
    conn.execute('DELETE FROM tests WHERE id=?', (test_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/tests/<test_id>/publish', methods=['PUT'])
@admin_required
def toggle_publish(test_id):
    conn = get_db()
    test = conn.execute('SELECT * FROM tests WHERE id=?', (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({'error': 'Test not found'}), 404
    
    # Check if test has questions before publishing
    count = conn.execute('SELECT COUNT(*) as c FROM questions WHERE test_id=?', (test_id,)).fetchone()['c']
    data = request.get_json()
    new_status = data.get('status', 'published')
    
    if new_status == 'published' and count == 0:
        conn.close()
        return jsonify({'error': 'Cannot publish a test with no questions'}), 400
    
    conn.execute('UPDATE tests SET status=?, updated_at=datetime("now") WHERE id=?', (new_status, test_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'status': new_status})


# ── Questions API ─────────────────────────────────────────────────────

@app.route('/api/tests/<test_id>/questions', methods=['GET'])
def get_questions(test_id):
    conn = get_db()
    questions = conn.execute(
        'SELECT * FROM questions WHERE test_id=? ORDER BY order_num ASC', (test_id,)
    ).fetchall()
    conn.close()
    
    is_admin = session.get('is_admin')
    result = []
    for q in questions:
        qd = dict(q)
        if not is_admin:
            # Don't expose correct answer to students
            del qd['correct_answer']
        result.append(qd)
    return jsonify(result)


@app.route('/api/tests/<test_id>/questions', methods=['POST'])
@admin_required
def create_question(test_id):
    conn = get_db()
    test = conn.execute('SELECT id FROM tests WHERE id=?', (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({'error': 'Test not found'}), 404
    
    data = request.get_json()
    question_text = data.get('question_text', '')
    question_image = data.get('question_image', '')
    option_a = data.get('option_a', '').strip()
    option_b = data.get('option_b', '').strip()
    option_c = data.get('option_c', '').strip()
    option_d = data.get('option_d', '').strip()
    correct_answer = data.get('correct_answer', '').strip().upper()
    
    if not question_text and not question_image:
        conn.close()
        return jsonify({'error': 'Question text or image is required'}), 400
    if not all([option_a, option_b, option_c, option_d]):
        conn.close()
        return jsonify({'error': 'All four options are required'}), 400
    if correct_answer not in ('A', 'B', 'C', 'D'):
        conn.close()
        return jsonify({'error': 'Correct answer must be A, B, C, or D'}), 400
    
    # Get next order number
    max_order = conn.execute(
        'SELECT COALESCE(MAX(order_num), -1) as m FROM questions WHERE test_id=?', (test_id,)
    ).fetchone()['m']
    
    q_id = str(uuid.uuid4())[:8]
    conn.execute(
        '''INSERT INTO questions (id, test_id, question_text, question_image, option_a, option_b, option_c, option_d, correct_answer, order_num)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (q_id, test_id, question_text, question_image, option_a, option_b, option_c, option_d, correct_answer, max_order + 1)
    )
    conn.commit()
    conn.close()
    return jsonify({'id': q_id, 'order_num': max_order + 1}), 201


@app.route('/api/tests/<test_id>/questions/<q_id>', methods=['PUT'])
@admin_required
def update_question(test_id, q_id):
    conn = get_db()
    q = conn.execute('SELECT * FROM questions WHERE id=? AND test_id=?', (q_id, test_id)).fetchone()
    if not q:
        conn.close()
        return jsonify({'error': 'Question not found'}), 404
    
    data = request.get_json()
    question_text = data.get('question_text', q['question_text'])
    question_image = data.get('question_image', q['question_image'])
    option_a = data.get('option_a', q['option_a']).strip()
    option_b = data.get('option_b', q['option_b']).strip()
    option_c = data.get('option_c', q['option_c']).strip()
    option_d = data.get('option_d', q['option_d']).strip()
    correct_answer = data.get('correct_answer', q['correct_answer']).strip().upper()
    
    if not question_text and not question_image:
        conn.close()
        return jsonify({'error': 'Question text or image is required'}), 400
    if not all([option_a, option_b, option_c, option_d]):
        conn.close()
        return jsonify({'error': 'All four options are required'}), 400
    if correct_answer not in ('A', 'B', 'C', 'D'):
        conn.close()
        return jsonify({'error': 'Correct answer must be A, B, C, or D'}), 400
    
    # If image changed, delete old one
    if question_image != q['question_image'] and q['question_image']:
        old_path = os.path.join(UPLOAD_DIR, q['question_image'])
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
    
    conn.execute(
        '''UPDATE questions SET question_text=?, question_image=?, option_a=?, option_b=?, option_c=?, option_d=?, correct_answer=?
           WHERE id=? AND test_id=?''',
        (question_text, question_image, option_a, option_b, option_c, option_d, correct_answer, q_id, test_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/tests/<test_id>/questions/<q_id>', methods=['DELETE'])
@admin_required
def delete_question(test_id, q_id):
    conn = get_db()
    q = conn.execute('SELECT question_image FROM questions WHERE id=? AND test_id=?', (q_id, test_id)).fetchone()
    if not q:
        conn.close()
        return jsonify({'error': 'Question not found'}), 404
    
    if q['question_image']:
        img_path = os.path.join(UPLOAD_DIR, q['question_image'])
        if os.path.exists(img_path):
            try:
                os.remove(img_path)
            except OSError:
                pass
    
    conn.execute('DELETE FROM questions WHERE id=? AND test_id=?', (q_id, test_id))
    # Reorder remaining questions
    remaining = conn.execute(
        'SELECT id FROM questions WHERE test_id=? ORDER BY order_num ASC', (test_id,)
    ).fetchall()
    for i, r in enumerate(remaining):
        conn.execute('UPDATE questions SET order_num=? WHERE id=?', (i, r['id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/tests/<test_id>/questions/reorder', methods=['PUT'])
@admin_required
def reorder_questions(test_id):
    data = request.get_json()
    question_ids = data.get('question_ids', [])
    conn = get_db()
    for i, qid in enumerate(question_ids):
        conn.execute('UPDATE questions SET order_num=? WHERE id=? AND test_id=?', (i, qid, test_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ── Upload API ────────────────────────────────────────────────────────

@app.route('/api/upload', methods=['POST'])
@admin_required
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed. Use PNG, JPG, JPEG, WEBP, or GIF'}), 400
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4().hex[:12]}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)
    
    # Check file size
    if os.path.getsize(filepath) > MAX_IMAGE_SIZE:
        os.remove(filepath)
        return jsonify({'error': 'Image too large (max 10MB)'}), 400
    
    return jsonify({'filename': filename, 'url': f'/uploads/{filename}'}), 201


@app.route('/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ── Submit Test API ───────────────────────────────────────────────────

@app.route('/api/tests/<test_id>/submit', methods=['POST'])
def submit_test(test_id):
    conn = get_db()
    test = conn.execute('SELECT * FROM tests WHERE id=?', (test_id,)).fetchone()
    if not test:
        conn.close()
        return jsonify({'error': 'Test not found'}), 404
    
    questions = conn.execute(
        'SELECT * FROM questions WHERE test_id=? ORDER BY order_num ASC', (test_id,)
    ).fetchall()
    conn.close()
    
    data = request.get_json()
    answers = data.get('answers', {})  # {question_id: 'A'|'B'|'C'|'D'}
    start_time = data.get('start_time', '')
    end_time = data.get('end_time', '')
    
    correct = 0
    wrong = 0
    unattempted = 0
    details = []
    
    for q in questions:
        qd = dict(q)
        user_answer = answers.get(q['id'], '')
        is_correct = False
        status = 'unattempted'
        
        if user_answer:
            if user_answer.upper() == q['correct_answer']:
                correct += 1
                is_correct = True
                status = 'correct'
            else:
                wrong += 1
                status = 'wrong'
        else:
            unattempted += 1
        
        details.append({
            'id': q['id'],
            'question_text': q['question_text'],
            'question_image': q['question_image'],
            'option_a': q['option_a'],
            'option_b': q['option_b'],
            'option_c': q['option_c'],
            'option_d': q['option_d'],
            'correct_answer': q['correct_answer'],
            'user_answer': user_answer,
            'is_correct': is_correct,
            'status': status
        })
    
    total = len(questions)
    percentage = round((correct / total * 100), 1) if total > 0 else 0
    
    return jsonify({
        'test_name': test['name'],
        'test_id': test_id,
        'total_questions': total,
        'correct': correct,
        'wrong': wrong,
        'unattempted': unattempted,
        'score': correct,
        'max_score': total,
        'percentage': percentage,
        'start_time': start_time,
        'end_time': end_time,
        'details': details
    })


# ── Dashboard Stats API ──────────────────────────────────────────────

@app.route('/api/stats', methods=['GET'])
@admin_required
def get_stats():
    conn = get_db()
    total_tests = conn.execute('SELECT COUNT(*) as c FROM tests').fetchone()['c']
    published = conn.execute("SELECT COUNT(*) as c FROM tests WHERE status='published'").fetchone()['c']
    drafts = conn.execute("SELECT COUNT(*) as c FROM tests WHERE status='draft'").fetchone()['c']
    total_questions = conn.execute('SELECT COUNT(*) as c FROM questions').fetchone()['c']
    conn.close()
    return jsonify({
        'total_tests': total_tests,
        'published': published,
        'drafts': drafts,
        'total_questions': total_questions
    })


# ── Initialize and Run ───────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print("\n  [HEART] MCQ Test Platform")
    print(f"  URL: http://localhost:5000")
    print(f"  Admin password: {ADMIN_PASSWORD}")
    print(f"  Database: {DB_PATH}")
    print(f"  Uploads: {UPLOAD_DIR}\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
