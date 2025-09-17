
import os
import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
if not HF_API_TOKEN:
    raise RuntimeError("Set HF_API_TOKEN in .env")

app = FastAPI()


mock_catalog = {
    "burrito": {"name": "burrito", "price": 8.5},
    "taco": {"name": "taco", "price": 3.0},
    "soda": {"name": "soda", "price": 1.5},
}

def query_hf_api(query: str) -> str:
    
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {"inputs": query}
    try:
        response = requests.post(
            "https://api-inference.huggingface.co/models/google/flan-t5-xl",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        output = response.json()
        # Depending on model, output can be list of dicts
        if isinstance(output, list) and "generated_text" in output[0]:
            return output[0]["generated_text"]
        elif isinstance(output, dict) and "generated_text" in output:
            return output["generated_text"]
        else:
            return "Sorry, I'm unable to answer right now."
    except Exception as e:
        print("HF API error:", e)
        return "Sorry, I'm unable to answer right now."

@app.post("/chat")
async def chat(payload: dict):
    query = payload.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="Provide 'query' in JSON body")

    query_lower = query.lower()
    item = mock_catalog.get(query_lower)

    if item and item["price"] is not None:
        answer = f"The {item['name']} costs ${item['price']:.2f}. Enjoy your meal!"
    else:
        answer = query_hf_api(query)

    return JSONResponse({"answer": answer, "catalog_count": len(mock_catalog)})

@app.get("/")
def home():
    return {
        "message": "Chatbot demo with mock catalog + Hugging Face fallback. POST JSON {'query': 'burrito'} to /chat"
    }
