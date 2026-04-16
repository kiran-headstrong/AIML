import os
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
load_dotenv()
 
 
# Initialize the model 
# (It automatically finds os.getenv("GROQ_API_KEY"))
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0
)
 
print(llm.invoke("The sky is .."))