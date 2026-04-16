import os
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()
api_key = os.getenv("HF_TOKEN")

# Initialize the client
client = InferenceClient(api_key=api_key)

def draft_email(notes):
    try:
        # Using a model that is guaranteed to support the chat interface
        response = client.chat.completions.create(
            model="meta-llama/Llama-3.2-3B-Instruct", 
            messages=[
                {"role": "system", "content": "You are a professional email assistant."},
                {"role": "user", "content": f"Draft a professional email based on these notes: {notes}"}
            ],
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

# --- Test ---
user_notes = "I'm running 15 minutes late for our sync."
print(draft_email(user_notes))
