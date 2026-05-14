import fitz

def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    pdf = fitz.open("pdf", file_bytes)
    text_parts = []
    
    # Optional terminal printing logic preserved for the user
    for page_num, page in enumerate(pdf):
        page_text = page.get_text()
        text_parts.append(page_text)
        print(f"Page {page_num + 1} preview: {page_text[:40].replace(chr(10), ' ')}")
        
    return "\n".join(text_parts).strip()
