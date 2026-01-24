from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import shutil
import os
import json
import requests
import io
import uuid # Import uuid for unique filenames
import tempfile # Not used in final code, but good to have if temp files are needed for other purposes

from app.services.ingestion import parse_file, chunk_text
from app.services.vector_store import VectorDB
from app.services.llm_engine import LLMEngine
from app.services.ppt_generator import create_ppt_from_json

app = FastAPI()
os.makedirs("storage", exist_ok=True)
os.makedirs("temp_images", exist_ok=True) # Directory for temporary images

# Initialize Services
vector_db = VectorDB()
llm = LLMEngine()

active_document: str = None
latest_llm_response_for_ppt: str = None


# Initialize active_document on startup if files exist
@app.on_event("startup")
async def startup_event():
    global active_document
    # Removed global google_web_search setup as it's passed explicitly
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

# Define a wrapper for the google_web_search tool
async def call_google_web_search(query: str):
    # This function acts as a wrapper for the agent's google_web_search tool.
    # The agent's execution environment should replace this call with the actual tool invocation.
    return await google_web_search(query=query)


async def search_and_download_image(query: str, download_dir: str = "temp_images") -> str | None:
    """
    Performs a Google web search for an image and downloads the first suitable result.
    Returns the local path to the downloaded image or None if no image is found.
    """
    try:
        search_query = f"{query} image"
        # Use the wrapper function to call the google_web_search tool
        search_results_raw = await call_google_web_search(query=search_query) 
        
        # Parse search results to find a direct image link
        image_url = None
        if search_results_raw and isinstance(search_results_raw, dict) and search_results_raw.get("items"):
            for item in search_results_raw["items"]:
                # Look for direct image links
                if item.get("fileFormat") and ("jpeg" in item["fileFormat"] or "png" in item["fileFormat"] or "gif" in item["fileFormat"]):
                    image_url = item.get("link")
                    break
                # Fallback to a link that might contain an image, and filter by common image extensions
                if item.get("link") and any(ext in item["link"].lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                    # Simple check for direct image links
                    if item["link"].lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        image_url = item.get("link")
                        break

        if not image_url:
            print(f"No suitable image found for query: {query}")
            return None

        print(f"Attempting to download image from: {image_url}")
        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx) 

        # Create a unique filename for the image
        file_extension = "jpg" # Default to jpg
        try:
            # Extract extension from URL, handling query parameters
            parsed_url = item["link"].split('?')[0] # Use item['link'] as it's the original link
            if '.' in parsed_url:
                ext = parsed_url.rsplit('.', 1)[1].lower()
                if ext in ['jpg', 'jpeg', 'png', 'gif']:
                    file_extension = ext
        except Exception:
            pass # Use default if extension extraction fails

        unique_filename = f"image_{uuid.uuid4()}.{file_extension}"
        image_path = os.path.join(download_dir, unique_filename)

        with open(image_path, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        print(f"Image downloaded to: {image_path}")
        return image_path

    except requests.exceptions.RequestException as req_err:
        print(f"HTTP/Network error downloading image for query '{query}': {req_err}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during image search/download for query '{query}': {e}")
        return None

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
        **Objective:** Provide a concise, comprehensive, and high-quality executive summary of the following document. 
        
        **Key Requirements:**
        1.  **Conciseness:** Aim for a summary that is approximately 300-500 words, unless the document is exceptionally short or long.
        2.  **Comprehensiveness:** Cover all major sections, themes, and significant findings of the document.
        3.  **Accuracy:** Ensure all information presented is directly supported by the document's content.
        4.  **Structure:** Organize the summary with clear headings and bullet points to enhance readability.
        5.  **Focus:** Highlight key arguments, methodologies (if applicable), results, and conclusions. Avoid redundancy.
        6.  **Audience:** Assume the summary is for a busy professional who needs to quickly grasp the essence of the document.
        
        **Document to Summarize:**
        {full_document_content}
        """
        response = llm.query(prompt)
        if response.startswith("Error:"):
            raise HTTPException(status_code=500, detail=response)
        
        global latest_llm_response_for_ppt
        latest_llm_response_for_ppt = response
        return {"summary": response}
    except Exception as e:
        print(f"Error in summarize_doc: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while generating the summary.")

@app.post("/generate-ppt")
async def generate_ppt():
    temp_image_paths = [] 
    try:
        global latest_llm_response_for_ppt
        if not latest_llm_response_for_ppt:
            raise HTTPException(status_code=400, detail="No LLM response available for PPT generation. Please ask a query or summarize a document first.")
        
        # Use the latest LLM response as the content for PPT generation
        content_for_ppt = latest_llm_response_for_ppt
        
        # JSON Prompt Engineering
        prompt = f"""
        **Objective:** Generate a detailed content plan for a professional PowerPoint presentation based on the following text, which is an LLM generated response (either a query answer or a summary).
        
        **Key Requirements:**
        1.  **Comprehensive Coverage:** Expand upon the key points and information present in the provided text.
        2.  **Slide Density:** Each slide should be packed with information, using concise bullet points and clear titles. Aim for a higher information density per slide.
        3.  **Structure:**
            *   Start with an introductory slide that sets the context of the provided text.
            *   Dedicate separate slides to main concepts, arguments, and supporting details derived from the text.
            *   Conclude with a summary or key takeaways.
        4.  **Format:** Output *only* a valid JSON object. Do not include any markdown formatting outside the JSON.
        
        **JSON Structure:**
        {{
            "presentation_title": "Descriptive Title for the Presentation (e.g., 'Presentation on [Topic from Text]')",
            "slides": [
                {{
                    "title": "Concise Slide Title",
                    "content": [
                        "Key point 1 (dense and informative)",
                        "Key point 2 (dense and informative)",
                        "..."
                    ],
                    "notes": "Optional speaker notes for this slide (keep concise)"
                }},
                // ... more slide objects ...
            ]
        }}
        
        **Provided Text (LLM Response):**
        {content_for_ppt}
        """
        
        json_response = llm.generate_json(prompt)
        if json_response.startswith("Error:"):
            raise HTTPException(status_code=500, detail=json_response)
        
        ppt_data = json.loads(json_response)
        presentation_title = ppt_data.get("presentation_title", "presentation")

        # --- Image Search and Download for each slide ---
        for slide_index, slide_data in enumerate(ppt_data.get("slides", [])):
            search_query = slide_data.get("title", "")
            if not search_query and slide_data.get("content"):
                content_sample = ""
                if isinstance(slide_data["content"], list) and slide_data["content"]:
                    content_sample = " ".join(slide_data["content"][0].split()[:10])
                elif isinstance(slide_data["content"], str):
                    content_sample = " ".join(slide_data["content"].split()[:10])
                search_query = content_sample
            
            if search_query:
                image_path = await search_and_download_image(query=search_query, download_dir="temp_images", google_web_search_tool=google_web_search)
                if image_path:
                    ppt_data["slides"][slide_index]["image_path"] = image_path
                    temp_image_paths.append(image_path)
                else:
                    print(f"No image found for slide: {search_query}")
            else:
                print(f"No valid search query for slide {slide_index}")
        
        file_path = create_ppt_from_json(json.dumps(ppt_data))
        
        if not file_path:
            raise HTTPException(status_code=500, detail="Failed to generate PPT from JSON content.")
            
        safe_title = "".join([c for c in presentation_title if c.isalnum() or c in (' ', '.', '_')]).rstrip()
        filename = f"{safe_title}.pptx" if safe_title else "presentation.pptx"
            
        return FileResponse(file_path, filename=filename, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    except Exception as e:
        print(f"Error in generate_ppt: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while generating the presentation.")
    finally:
        for path in temp_image_paths:
            if os.path.exists(path):
                os.remove(path)
                print(f"Cleaned up temporary image: {path}")