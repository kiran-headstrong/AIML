"""
Gemma 4 E2B - Local inference via Ollama
OpenAI-compatible API at http://localhost:11434/v1
"""

from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",  # required but unused
)

MODEL = "gemma4-fast"  # optimized: 4096 ctx, no thinking mode, 8 threads

def chat(messages: list[dict], think: bool = False) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=1.0,
        top_p=0.95,
        extra_body={"think": think},  # disable Gemma 4 internal reasoning for speed
    )
    return response.choices[0].message.content

def main():
    print(f"Chatting with {MODEL} — type 'quit' to exit\n")
    history = []

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})
        reply = chat(history)
        history.append({"role": "assistant", "content": reply})
        print(f"\nGemma 4: {reply}\n")

if __name__ == "__main__":
    main()
