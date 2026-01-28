import sys
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, ArrayObject, NumberObject
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTAnno

def highlight_evidence_pure(pdf_path, output_path, evidence):
    """
    Args:
        evidence: list of dicts [{"label": str, "quote": str, "gemini_page": int|None}]
        
    Returns:
        citation_map: {label: {"page": int, "status": "verified"|"unverified"}}
    """
    # Helper to clean and normalize quotes (collapse whitespace for matching)
    import re
    def clean(q):
        if not q:
            return None
        # Normalize: lowercase, collapse all whitespace to single space
        return re.sub(r'\s+', ' ', q.strip().lower())

    # Map quote_lower -> list of labels that use this quote
    target_map = {}
    valid_evidence_count = 0
    
    for item in evidence:
        q = clean(item.get("quote"))
        if q:
            if q not in target_map:
                target_map[q] = []
            target_map[q].append(item["label"])
            valid_evidence_count += 1
            
    targets_lower = list(target_map.keys())
    print(f"Searching for {valid_evidence_count} quotes ({len(targets_lower)} unique strings)...")
    
    matches = {} # {page_index: [list of quad_points_lists]}
    
    # Initialize results with labels
    # We will fill this in as we find them. 
    # If not found after scan, we fill with fallback.
    citation_map = {} 
    
    try:
        pages_generator = extract_pages(pdf_path)
    except Exception as e:
        print(f"Error reading PDF with pdfminer: {e}")
        return {}

    match_count = 0
    page_idx = 0
    
    while True:
        try:
            page_layout = next(pages_generator)
        except StopIteration:
            break
        except Exception as e:
            print(f"Error extracting content from page {page_idx}: {e}")
            break

        full_text = ""
        char_map = [] # list of (char_bbox or None)

        def extract_text_recursive(element):
            nonlocal full_text
            if isinstance(element, LTChar):
                full_text += element.get_text()
                char_map.append(element.bbox)
            elif isinstance(element, LTAnno):
                text = element.get_text()
                if text == '\n':
                    full_text += ' '
                    char_map.append(None)
                else:
                    full_text += text
                    char_map.append(None)
            elif hasattr(element, '__iter__'):
                for child in element:
                    extract_text_recursive(child)
        
        extract_text_recursive(page_layout)

        # Normalize full_text for searching (collapse whitespace)
        # But we need to map normalized indices back to original char_map
        normalized_text = ""
        norm_to_orig = []  # norm_to_orig[norm_idx] = orig_idx
        
        i = 0
        while i < len(full_text):
            c = full_text[i]
            if c.isspace():
                # Collapse consecutive whitespace to single space
                if normalized_text and not normalized_text.endswith(' '):
                    normalized_text += ' '
                    norm_to_orig.append(i)
                i += 1
                while i < len(full_text) and full_text[i].isspace():
                    i += 1
            else:
                normalized_text += c.lower()
                norm_to_orig.append(i)
                i += 1
        
        page_quads = []
        
        # Search for EACH unique target on this page
        for target in targets_lower:
            start_idx = 0
            while True:
                idx = normalized_text.find(target, start_idx)
                if idx == -1:
                    break
                
                # Match found - map normalized indices back to original
                orig_indices = [norm_to_orig[i] for i in range(idx, idx + len(target)) if i < len(norm_to_orig)]
                raw_bboxes = [char_map[oi] for oi in orig_indices if oi < len(char_map)]
                matched_bboxes = [b for b in raw_bboxes if b is not None]

                if matched_bboxes:
                     # Identify which labels verified by this quote
                    labels = target_map[target]
                    
                    # For each label associated with this quote text
                    for lbl in labels:
                        if lbl not in citation_map:
                            # Not yet found -> Mark Verified!
                            citation_map[lbl] = {
                                "page": page_idx + 1,
                                "status": "verified"
                            }
                    
                    # Logic: We might want to highlight ALL instances, 
                    # but only record the first page for navigation?
                    # Yes.
                    
                    # Group by line
                    matched_bboxes.sort(key=lambda b: b[3], reverse=True)
                    
                    lines = []
                    if matched_bboxes:
                        current_line = [matched_bboxes[0]]
                        for b in matched_bboxes[1:]:
                            if abs(b[3] - current_line[0][3]) > 5:
                                lines.append(current_line)
                                current_line = [b]
                            else:
                                current_line.append(b)
                        lines.append(current_line)
                    
                    instance_quads = []
                    for line_bboxes in lines:
                        x0 = min(b[0] for b in line_bboxes)
                        y0 = min(b[1] for b in line_bboxes)
                        x1 = max(b[2] for b in line_bboxes)
                        y1 = max(b[3] for b in line_bboxes)
                        instance_quads.extend([x0, y1, x1, y1, x0, y0, x1, y0])
                    
                    page_quads.append(instance_quads)
                    match_count += 1
                
                start_idx = idx + 1 
        
        if page_quads:
            matches[page_idx] = page_quads
        
        page_idx += 1

    # --- Fallback Logic ---
    # For any Evidence Label NOT in citation_map, checks fallback
    for item in evidence:
        lbl = item["label"]
        if lbl not in citation_map:
            # Not verified by text search
            fallback_page = item.get("gemini_page")
            
            # Safety conversion
            try:
                if fallback_page:
                    fallback_page = int(fallback_page)
            except:
                fallback_page = None
                
            if fallback_page:
                citation_map[lbl] = {
                    "page": fallback_page,
                    "status": "unverified" # Warn user
                }
            else:
                citation_map[lbl] = {
                    "page": None,
                    "status": "missing"
                }

    # Write highlights (Only for Verify matches)
    # We always write the PDF, even if no highlights, to keep consistent path
    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        
        for i, page in enumerate(reader.pages):
            writer.add_page(page)
            
            if i in matches:
                for quads in matches[i]:
                    xs = quads[0::2]
                    ys = quads[1::2]
                    if not xs or not ys: continue
                    
                    x_min, x_max = min(xs), max(xs)
                    y_min, y_max = min(ys), max(ys)
                    
                    annot = DictionaryObject()
                    annot[NameObject("/Type")] = NameObject("/Annot")
                    annot[NameObject("/Subtype")] = NameObject("/Highlight")
                    annot[NameObject("/F")] = NumberObject(4)
                    annot[NameObject("/Rect")] = ArrayObject([NumberObject(n) for n in [x_min, y_min, x_max, y_max]])
                    annot[NameObject("/QuadPoints")] = ArrayObject([NumberObject(n) for n in quads])
                    annot[NameObject("/C")] = ArrayObject([NumberObject(1), NumberObject(1), NumberObject(0)])
                    
                    writer.add_annotation(page_number=i, annotation=annot)

        writer.write(output_path)
        print(f"Saved highlighted PDF to: {output_path}")

    except Exception as e:
        print(f"Error saving PDF with pypdf: {e}")
    
    return citation_map

if __name__ == "__main__":
    if len(sys.argv) > 3:
        # Backward compatibility or simpler test?
        # Let's say args are: pdf in, pdf out, "label1:quote1:page1" ...
        # Too complex for CLI now. Just generic test.
        print("CLI testing updated. Use app.py.")
    else:
        print("Usage: python highlight_evidence_pure.py <input_pdf> <output_pdf> ...")
