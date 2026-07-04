## Enterprise RAG System

A Retrieval-Augmented Generation (RAG) backend built with FastAPI, designed 
to ingest, chunk, and index enterprise documents (PDF, DOCX, TXT) for 
semantic search and question-answering.

### Key Features
- **Structure-aware document loading** — extracts heading hierarchy from 
  DOCX files natively and via heuristic detection in PDFs, preserving 
  section context (e.g. "Chapter 2 > Installation") alongside extracted text
- **Hybrid chunking strategy** — combines semantic similarity (via Gemini 
  embeddings) with structural boundaries, splitting only when both topic 
  and section change, with dynamic per-document similarity thresholds
- **Hybrid retrieval** — dense vector search via Qdrant (cosine similarity) 
  paired with sparse BM25 keyword search for balanced semantic + lexical 
  matching
- **Production-oriented reliability** — batched embedding requests, 
  exponential backoff on rate limits, deterministic vector IDs to prevent 
  duplicate indexing on reprocessing

### Tech Stack
FastAPI · Qdrant · Google Gemini (embeddings) · rank-bm25 · pypdf · 
python-docx

### Architecture
```
Raw Document (PDF/DOCX/TXT)
    → Structured Loading (section-aware block extraction)
    → Semantic + Structural Chunking
    → Dual Indexing (Qdrant dense + BM25 sparse)
```
