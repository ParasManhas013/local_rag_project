from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import shutil
import os
import json
# Removed requests, io, uuid, tempfile as they are no longer needed for image search in main.py

from app.services.ingestion import parse_file, chunk_text
from app.services.vector_store import VectorDB
from app.services.llm_engine import LLMEngine
from app.services.ppt_generator import create_ppt_from_json

app = FastAPI()
os.makedirs("storage", exist_ok=True)
# Removed os.makedirs("temp_images", exist_ok=True)

# Initialize Services
vector_db = VectorDB()
llm = LLMEngine()

active_document: str = None
latest_llm_response_for_ppt: str = None
ppt_history: list = []
# Removed latest_llm_response_for_ppt: str = None


# Initialize active_document on startup if files exist
@app.on_event("startup")
async def startup_event():
    global active_document
    files_in_storage = [f for f in os.listdir("storage") if os.path.isfile(os.path.join("storage", f))]
    if files_in_storage:
        active_document = files_in_storage[0]
        print(f"Active document set to: {active_document} from storage on startup.")
    else:
        print("No documents in storage on startup.")

def _get_active_document_or_raise():
    global active_document
    if not active_document:
        raise HTTPException(status_code=400, detail="No document selected. Please upload or select a document first.")
    return active_document

# Removed call_google_web_search and search_and_download_image functions

# Serve Frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

class QueryRequest(BaseModel):
    query: str

class FileContentRequest(BaseModel):
    filename: str

@app.post("/get-file-content")
async def get_file_content(request: FileContentRequest):
    file_path = f"storage/{request.filename}"
    if os.path.exists(file_path):
        content = parse_file(file_path, request.filename)
        return {"filename": request.filename, "content": content}
    else:
        raise HTTPException(status_code=404, detail="File not found.")

class DeleteRequest(BaseModel):
    filename: str

@app.post("/delete-file")
async def delete_file(request: DeleteRequest):
    file_path = f"storage/{request.filename}"
    if os.path.exists(file_path):
        os.remove(file_path)
        vector_db.delete_document(request.filename) 
        
        global active_document
        if active_document == request.filename:
            active_document = None
            
        return {"status": "success", "message": f"File '{request.filename}' deleted."}
    else:
        raise HTTPException(status_code=404, detail="File not found.")

@app.get("/list-files")
async def list_files():
    files = [f for f in os.listdir("storage") if os.path.isfile(os.path.join("storage", f))]
    global active_document
    return {"files": files, "active_document": active_document}

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    file_path = f"storage/{file.filename}"

    if os.path.exists(file_path):
        vector_db.delete_document(file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Pipeline: Parse -> Chunk -> Embed -> Store
    raw_text = parse_file(file_path, file.filename)
    chunks = chunk_text(raw_text)
    vector_db.add_documents(chunks, [{"source": file.filename} for _ in chunks])
    
    global active_document
    active_document = file.filename
    
    return {"status": "success", "chunks_processed": len(chunks), "active_document": active_document}

class SetActiveDocumentRequest(BaseModel):
    filename: str

@app.post("/set-active-document")
async def set_active_document(request: SetActiveDocumentRequest):
    global active_document
    file_path = f"storage/{request.filename}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found in storage.")
    
    active_document = request.filename
    return {"status": "success", "active_document": active_document}

@app.post("/query")
async def rag_query(request: QueryRequest):
    try:
        current_active_document = _get_active_document_or_raise()
        # Retrieval
        context_chunks = vector_db.search(request.query, filename=current_active_document)
        context_text = "\n".join(context_chunks)
        
        # Augmented Generation
        prompt = f"""
        Context information is below.
        ---------------------
        {context_text}
        ---------------------
        Given the context information and not prior knowledge, answer the query.
        Query: {request.query}
        Answer:
        """
        response = llm.query(prompt)
        if response.startswith("Error:"):
            raise HTTPException(status_code=500, detail=response)
        
        global latest_llm_response_for_ppt
        latest_llm_response_for_ppt = response
        
        # Removed global latest_llm_response_for_ppt assignment
        return {"answer": response, "context": context_chunks}
    except Exception as e:
        print(f"Error in RAG query: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the query.")

@app.post("/summarize")
async def summarize_doc():
    try:
        current_active_document = _get_active_document_or_raise()
        file_path = f"storage/{current_active_document}"
        
        full_document_content = parse_file(file_path, current_active_document)
        
        prompt = f"""
        **Objective:** Provide a detailed, comprehensive, and high-quality executive summary of the following document. 
        
        **Key Requirements:**
        1.  **Comprehensiveness:** Cover all major sections, themes, and significant findings of the document.
        2.  **Accuracy:** Ensure all information presented is directly supported by the document's content.
        3.  **Structure:** Organize the summary with clear headings and bullet points to enhance readability.
        4.  **Focus:** Highlight key arguments, methodologies (if applicable), results and conclusions. Avoid redundancy.
        5.  **Audience:** Assume the summary is for a busy professional who needs to quickly grasp the essence of the document.
        
        **Document to Summarize:**
        {full_document_content}
        """
        response = llm.query(prompt)
        if response.startswith("Error:"):
            raise HTTPException(status_code=500, detail=response)
        
        global latest_llm_response_for_ppt
        latest_llm_response_for_ppt = response
        
        # Removed global latest_llm_response_for_ppt assignment
        return {"summary": response}
    except Exception as e:
        print(f"Error in summarize_doc: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while generating the summary.")

@app.post("/generate-ppt")
async def generate_ppt():
    try:
        global latest_llm_response_for_ppt
        global ppt_history
        if not latest_llm_response_for_ppt:
            raise HTTPException(status_code=400, detail="No latest LLM message available to generate PPT. Please query or summarize a document first.")
        
        # State Capture
        ppt_history.append(latest_llm_response_for_ppt)
        
        # JSON Prompt Engineering to convert the latest LLM response into PPT format
        prompt = f"""
        **Objective:** Map the provided LLM response content into a strict 9-slide PowerPoint structure.
        
        **Constraint:** You are filling a pre-existing template with exactly 9 content slots. Do not create more slides. Fill the existing ones.
        
        **Template Structure & Content Requirements:**
        1.  **Slide 0 (Title Slide):**
            *   "title": Main Presentation Title
            *   "subtitle": A brief 1-sentence summary or subtitle.
        2.  **Slide 1 (Introduction):**
            *   "title": "Introduction" or similar.
            *   "content": [List of 3-4 bullet points introducing the topic]
        3.  **Slide 2 (Key Concept 1):**
            *   "title": Title of the first main section.
            *   "content": [List of 3-5 detailed bullet points]
        4.  **Slide 3 (Key Concept 2):**
            *   "title": Title of the second main section.
            *   "content": [List of 3-5 detailed bullet points]
        5.  **Slide 4 (Key Concept 3):**
            *   "title": Title of the third main section.
            *   "content": [List of 3-5 detailed bullet points]
        6.  **Slide 5 (Deep Dive / Data):**
            *   "title": Title for a detailed analysis or data section.
            *   "content": [List of 3-5 detailed bullet points]
        7.  **Slide 6 (Technology / Methodology):**
            *   "title": Title regarding methods or tech.
            *   "content": [List of 3-5 detailed bullet points]
        8.  **Slide 7 (Security / Risks):**
            *   "title": Title regarding security, risks, or challenges.
            *   "content": [List of 3-5 detailed bullet points]
        9.  **Slide 8 (Conclusion / Impact):**
            *   "title": "Conclusion" or "Future Impact".
            *   "content": [List of 3-4 closing thoughts]

        **Format:** Output *only* a valid JSON object.
        
        **JSON Output Schema:**
        {{
            "presentation_title": "Filename",
            "slides": [
                {{ "title": "...", "subtitle": "..." }}, // Slide 0
                {{ "title": "...", "content": ["Point 1", "Point 2"] }}, // Slide 1
                {{ "title": "...", "content": ["Point 1", "Point 2"] }}, // Slide 2
                // ... continue for all 9 slides ...
            ]
        }}
        
        **LLM Response to be transformed:**
        {latest_llm_response_for_ppt}
        """
        
        json_response = llm.generate_json(prompt)
        if json_response.startswith("Error:"):
            raise HTTPException(status_code=500, detail=json_response)
        
        ppt_data = json.loads(json_response)
        presentation_title = ppt_data.get("presentation_title", "presentation")

        file_path = create_ppt_from_json(json.dumps(ppt_data))

        if not file_path:
            raise HTTPException(status_code=500, detail="Failed to generate PPT from JSON content.")
            
        safe_title = "".join([c for c in presentation_title if c.isalnum() or c in (' ', '.', '_')]).rstrip()
        filename = f"{safe_title}.pptx" if safe_title else "presentation.pptx"
                
        return FileResponse(file_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")

    except Exception as e:
        print(f"Error in generate_ppt: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while generating the presentation.")