# Local RAG Project 🚀

## 🔍 Overview

This project is a **fully local Retrieval-Augmented Generation (RAG) system** with **document ingestion, semantic search, summarization, and PPT generation**.

You can:
- Upload local documents (PDF / TXT / DOCX)
- Ask questions using semantic retrieval
- Summarize entire documents
- **Generate PowerPoint (PPT) presentations from documents or summaries**
- Run everything locally (LLM + Vector DB)

Designed for **privacy-preserving AI applications**, academic use, and demos.

---

## ✨ Key Features

✅ Local document ingestion  
✅ Semantic retrieval using vector embeddings  
✅ LLM-powered Q&A  
✅ One-click **document summarization**  
✅ **PPT generation**  
✅ Works with **local LLMs (LLaMA / Ollama / GPT4All)**  
✅ No cloud dependency required  

---

## 🧠 Tech Stack

| Component | Tool |
|---------|------|
| Language | Python |
| RAG Framework | LangChain |
| Vector DB | ChromaDB |
| Embeddings | Sentence Transformers |
| LLM | LLaMA / Ollama |
| PPT Generation | python-pptx |
| UI | HTML / CSS / JS |

---

## Launch the app:
bash

uvicorn app.main:app --reload


