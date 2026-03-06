import os
import json
import numpy as np
from docx import Document

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")

_company_chunks = {}

def load_company_docs():
    companies = ["Microsoft", "Amazon"]
    for company in companies:
        path = os.path.join(DATA_DIR, f"{company}.docx")
        if not os.path.exists(path):
            print(f"⚠️  {company}.docx not found in data/")
            continue
        doc = Document(path)
        chunks = []
        current = ""
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            current += " " + text
            if len(current) > 600:
                chunks.append(current.strip())
                current = ""
        if current.strip():
            chunks.append(current.strip())
        _company_chunks[company.lower()] = chunks
        print(f"✅ Loaded {len(chunks)} chunks from {company}.docx")

def get_context(company: str, query: str, n=5) -> str:
    chunks = _company_chunks.get(company.lower(), [])
    if not chunks:
        return ""
    # Simple keyword scoring — no vector DB needed
    query_words = set(query.lower().split())
    scored = []
    for chunk in chunks:
        chunk_words = set(chunk.lower().split())
        score = len(query_words & chunk_words)
        scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [c for _, c in scored[:n] if _ > 0] or [c for _, c in scored[:3]]
    return "\n\n".join(top)

load_company_docs()