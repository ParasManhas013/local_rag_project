import os
from pypdf import PdfReader
from docx import Document

def parse_file(file_path: str, filename: str):
    ext = filename.split('.')[-1].lower()
    text = ""
    
    if ext == 'pdf':
        reader = PdfReader(file_path)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    elif ext == 'docx':
        doc = Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    elif ext == 'txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
            
    return text

def chunk_text(text: str, chunk_size=500, overlap=50):
    # Sliding window chunking
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += (chunk_size - overlap)
    return chunks