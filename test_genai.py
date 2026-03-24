import os
from dotenv import load_dotenv
from google.genai import Client
import inspect

load_dotenv()
client = Client(api_key=os.getenv("GOOGLE_API_KEY"))
print(inspect.signature(client.operations.get))
