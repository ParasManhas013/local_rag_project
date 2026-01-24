import ollama

class LLMEngine:
    def __init__(self, model="llama3.1:8b"):
        self.model = model

    def query(self, prompt: str, system_prompt: str = None):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = ollama.chat(model=self.model, messages=messages)
            return response['message']['content']
        except ollama.ResponseError as e:
            print(f"Ollama connection error: {e}")
            return "Error: Could not connect to Ollama. Please make sure Ollama is running and the model is installed."

    def generate_json(self, prompt: str):
        try:
            # Enforce JSON mode (supported in newer Ollama versions)
            response = ollama.chat(
                model=self.model, 
                messages=[{"role": "user", "content": prompt}],
                format="json" 
            )
            return response['message']['content']
        except ollama.ResponseError as e:
            print(f"Ollama connection error: {e}")
            return "Error: Could not connect to Ollama. Please make sure Ollama is running and the model is installed."