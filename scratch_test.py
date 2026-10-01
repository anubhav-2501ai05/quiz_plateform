import fitz
import re

PDF_PATH = r"C:\Users\kumar\Downloads\17-December-2024-Shift-1-English.pdf"

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

doc = fitz.open(PDF_PATH)
questions_data = []
table_images = {} # Will leave empty for now

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
        
        questions_data.append({
            'num': q_num,
            'question_text': q_text,
            'option_a': opt_a,
            'option_b': opt_b,
            'option_c': opt_c,
            'option_d': opt_d,
            'correct_answer': correct_letter
        })

print(f"Parsed {len(questions_data)} questions.")
for q in questions_data:
    if q['num'] in [13, 17, 99, 100, 7, 47, 54]:
        print(f"--- Q.{q['num']} ---")
        print(q['question_text'])
        print(f"A: {q['option_a']}")
        print(f"B: {q['option_b']}")
        print(f"C: {q['option_c']}")
        print(f"D: {q['option_d']}")
        print(f"Correct: {q['correct_answer']}")
