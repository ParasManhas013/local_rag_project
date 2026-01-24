import chromadb
from sentence_transformers import SentenceTransformer
import uuid

class VectorDB:
    def __init__(self):
        self.collection_name = "local_docs"
        self.client = chromadb.PersistentClient(path="storage/chroma_db")
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2') 
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
        )

    def add_documents(self, chunks: list[str], meta: list[dict]):
        embeddings = self.encoder.encode(chunks)
        documents = chunks
        metadatas = meta
        ids = [str(uuid.uuid4()) for _ in documents]

        self.collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )

    def search(self, query: str, top_k: int = 5, filename: str = None):
        query_embedding = self.encoder.encode([query])
        where_clause = {"source": filename} if filename else {}
        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            where=where_clause
        )
        return results['documents'][0]

    def delete_document(self, filename: str):
        """Deletes all chunks associated with a specific filename from the collection."""
        self.collection.delete(where={"source": filename})