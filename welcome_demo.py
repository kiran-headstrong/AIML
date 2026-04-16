import os 
from dotenv import load_dotenv
from groq import Groq
# 1. Load the variables from your .env file into the system
load_dotenv()

# 2. Get the specific key from the system environment
# 3. Pass that key to the Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_email(rough_note, tone="professional"):
    prompt = f"Rewrite the following rough note into a {tone} email:\n\n{rough_note}"
    
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a helpful assistant that writes clear emails."},
                {"role": "user", "content": prompt}
            ],
            # CHANGED: Using a supported production model
            model="llama-3.3-70b-versatile", 
            temperature=0.7,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"

# --- Example Usage ---
print("--- Professional Email Generator ---")
user_note = input("Enter your rough note: ") 
print("\nGenerated Email:\n" + "-"*20)
print(generate_email(user_note))
