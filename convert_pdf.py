import fitz  # PyMuPDF
import os

pdf_path = "proposal.pdf"
output_dir = "static/proposal_images"

os.makedirs(output_dir, exist_ok=True)

try:
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=150) # High quality
        output_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
        pix.save(output_path)
        print(f"Saved {output_path}")
    print("Conversion complete.")
except Exception as e:
    print(f"Error: {e}")
