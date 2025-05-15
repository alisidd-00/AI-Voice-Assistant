# app/services/rag.py

import os
import base64
import requests

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.config import OPENROUTER_API_KEY, OPENROUTER_URL

# ─── OpenAI embedding client ─────────────────────────────────────────────────
OPENAI_KEY    = os.getenv("OPENAI_KEY")
_embed_client = OpenAI(api_key=OPENAI_KEY)
EMBED_MODEL   = "text-embedding-3-large"

# ─── Qdrant client ─────────────────────────────────────────────────────────────
QDRANT_URL     = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
_qdrant        = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def extract_text_from_pdf_with_gemini(pdf_buffer: bytes) -> str:
    """
    Send a PDF to OpenRouter’s chat/completions endpoint (Gemini 2.5),
    extract all its text faithfully, and return that text.
    """
    # 1) Encode PDF to data URL
    b64      = base64.b64encode(pdf_buffer).decode("utf-8")
    data_url = f"data:application/pdf;base64,{b64}"

    # 2) Build payload
    messages = [{
        "role": "user",
        "content": [
            {"type":"text", "text":(
                "Extract ALL text from the PDF document exactly as written, preserving:"
                """- Field labels and their corresponding values on the same line (e.g., "Client: Amaala Company")"""
                "- Original formatting and spacing between fields and values"
                "- Tables as markdown"
                "- Headers/footers"
                "- Text orientation"
                "- Special characters"
                "- Page numbers"
                "- Section headings"
                "- Bullet points/numbered lists"
                "- Alignment of field-value pairs"

                "Ensure field labels and their values remain together, even if they appear in columns or special formatting."
                "Return only the extracted text with no additions."
            )},
            
            {"type":"file", "file": {
                "filename":"document.pdf",
                "file_data":data_url
            }}
        ]
    }]

    payload = {
        "model":    "google/gemini-2.0-flash-001",
        "messages": messages,
        "plugins":  [{"id":"file-parser","pdf":{"engine":"pdf-text"}}]
    }
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json"
    }

    resp = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=120)
    if resp.status_code != 200:
        print("OpenRouter 400 body:", resp.text)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _chunk_text(
    text: str,
    chunk_size: int   = 512,
    chunk_overlap: int = 50
) -> list[str]:
    """
    Recursively split on ["\n\n", "\n", " ", ""]
    so no chunk > chunk_size characters, with chunk_overlap overlap.
    """
    splitter = RecursiveCharacterTextSplitter(
        separators=["\n\n", "\n", " ", ""],
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    return splitter.split_text(text)


def extract_and_index(
    assistant_id: int,
    user_id:      int,
    docs:         list[str|bytes],
) -> dict:
    """
    For each doc (bytes=PDF or str=text):
      - extract text if needed
      - chunk recursively
      - embed each chunk
      - upsert into Qdrant under "assistant_{assistant_id}_user_{user_id}"
    Returns how many chunks were indexed.
    """
    all_chunks: list[str] = []

    # 1) Extract & chunk
    for doc in docs:
        txt = extract_text_from_pdf_with_gemini(doc) if isinstance(doc, (bytes, bytearray)) else doc
        all_chunks.extend(_chunk_text(txt))

    if not all_chunks:
        return {"indexed": 0}

    # 2) Embed
    embeddings = []
    for chunk in all_chunks:
        resp = _embed_client.embeddings.create(input=chunk, model=EMBED_MODEL)
        embeddings.append(resp.data[0].embedding)

    # 3) Prepare Qdrant PointStructs
    points = []
    for idx, (chunk, vect) in enumerate(zip(all_chunks, embeddings)):
        points.append(
            rest.PointStruct(
                id=idx,
                vector=vect,
                payload={
                    "assistant_id": assistant_id,
                    "user_id":      user_id,
                    "text":         chunk
                }
            )
        )

    # 4) Re-create & upsert
    coll = f"assistant_{assistant_id}_user_{user_id}"
    _qdrant.recreate_collection(
        collection_name=coll,
        vectors_config=rest.VectorParams(
            size=len(embeddings[0]),
            distance=rest.Distance.COSINE
        )
    )
    _qdrant.upsert(collection_name=coll, points=points)

    return {"indexed": len(points)}
