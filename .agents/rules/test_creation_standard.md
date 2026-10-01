# Standard Rules for Test Creation from PDFs

Whenever you are asked to parse a PDF and create a new test for this MCQ platform, you MUST follow these exact standards to avoid regressions:

1. **Multiline Text Preservation**: 
   - Never flatten lines of text. Use the exact `y` coordinates of the text spans to determine line breaks. If the `y` coordinate changes, insert a `\n` to preserve the original multiline structure of questions and options.
   - Example implementation: Group spans into lines based on `s['bbox'][1]` (with a tolerance like `4`), assign a `line_id` to each span, and append a newline when the `line_id` changes during string assembly.

2. **Perfect Image Cropping**:
   - Do NOT just use `page.get_image_rects(xref)` blindly. Embedded graphics often have bounding boxes that overlap with surrounding text (like options).
   - If a question contains a graphic/table, you MUST calculate the bounding box (`fitz.Rect`) precisely. 
   - Ensure the crop perfectly frames ONLY the question text and the graphic. You must strictly exclude the "Ans" block and the multiple-choice options.

3. **In-place Updates**:
   - If fixing an existing test, DO NOT create a new test via the API. Update the local `data.db` inplace and use `PUT /api/tests/<test_id>/questions/<q_id>` to update the live Render platform inplace.
   - Any remote images uploaded via the Render API must be permanently saved in the local `uploads/` directory with their generated UUID filenames and pushed to GitHub. This prevents them from being wiped when Render automatically redeploys from the Git repository.

4. **Green Checkmark Answers**:
   - Use `page.get_text('dict')` and verify the color of the text (e.g., `s['color'] == 32768`) to accurately detect the correct answer option indicated by the green checkmark in the source PDF.
