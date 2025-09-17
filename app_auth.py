import os
import secrets
import urllib.parse
from typing import Dict

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
import httpx
import openai
from dotenv import load_dotenv

load_dotenv()

# Config
SQUARE_APP_ID = os.getenv("SQUARE_APP_ID")
SQUARE_APP_SECRET = os.getenv("SQUARE_APP_SECRET")
SQUARE_REDIRECT_URI = os.getenv("SQUARE_REDIRECT_URI")
SQUARE_ENV = os.getenv("SQUARE_ENVIRONMENT", "sandbox")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not (SQUARE_APP_ID and SQUARE_APP_SECRET and OPENAI_API_KEY):
    raise RuntimeError("Set SQUARE_APP_ID, SQUARE_APP_SECRET, and OPENAI_API_KEY in .env")

openai.api_key = OPENAI_API_KEY

SQUARE_BASE = "https://connect.squareupsandbox.com" if SQUARE_ENV=="sandbox" else "https://connect.squareup.com"
AUTHORIZE_URL = f"{SQUARE_BASE}/oauth2/authorize"
TOKEN_URL = f"{SQUARE_BASE}/oauth2/token"
CATALOG_LIST_ENDPOINT = f"{SQUARE_BASE}/v2/catalog/list"

app = FastAPI()

# In-memory token store for demo
token_store: Dict[str, Dict] = {}

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse("""
    <h2>Square OAuth + Chatbot Demo</h2>
    <a href="/authorize">Authorize with Square (Sandbox)</a>
    """)

@app.get("/authorize")
def authorize():
    state = secrets.token_urlsafe(16)
    token_store[state] = {"state": state}
    scope = "ITEMS_READ"
    params = {
        "client_id": SQUARE_APP_ID,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": SQUARE_REDIRECT_URI,
        "state": state
    }
    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)
    return HTMLResponse(f'<a href="{url}">Click here to authorize Square</a>')

@app.get("/callback", response_class=HTMLResponse)
async def callback(code: str = None, state: str = None, error: str = None):
    if error:
        return HTMLResponse(f"<p>Authorization error: {error}</p>")
    if not code or state not in token_store:
        raise HTTPException(status_code=400, detail="Missing code or invalid state")

    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, json={
            "client_id": SQUARE_APP_ID,
            "client_secret": SQUARE_APP_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": SQUARE_REDIRECT_URI
        })
        data = resp.json()
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=data)
        token_store[state].update(data)

    return HTMLResponse(f"""
    <h3>Authorization successful</h3>
    <p>Merchant ID: {data.get('merchant_id')}</p>
    <p>State: {state}</p>
    <p>Now POST JSON: {{'state': '{state}', 'query': 'How much is the burrito?'}} to /chat</p>
    """)

async def fetch_catalog(access_token: str):
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json", "Square-Version": "2025-08-20"}
    params = {"types": "ITEM"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(CATALOG_LIST_ENDPOINT, headers=headers, params=params)
        resp.raise_for_status()
        items = {}
        for obj in resp.json().get("objects", []):
            if obj.get("type")=="ITEM":
                name = obj["item_data"]["name"]
                variations = obj["item_data"].get("variations", [])
                price = None
                if variations:
                    price_money = variations[0]["item_variation_data"].get("price_money")
                    if price_money: price = price_money["amount"]/100
                items[name.lower()] = {"name": name, "price": price}
        return items

def build_prompt(query, catalog):
    catalog_text = "\n".join([f"- {v['name']}: ${v['price']:.2f}" for v in catalog.values()])
    return f"You are a helpful store assistant.\nCatalog:\n{catalog_text}\nUser asked: {query}\nAnswer concisely."

@app.post("/chat")
async def chat(payload: dict):
    state = payload.get("state")
    query = payload.get("query")
    if not state or not query: raise HTTPException(status_code=400, detail="Provide state and query")
    token_info = token_store.get(state)
    if not token_info or "access_token" not in token_info: raise HTTPException(status_code=400, detail="No token for state")

    catalog = await fetch_catalog(token_info["access_token"])
    prompt = build_prompt(query, catalog)
    response = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
    answer = response["choices"][0]["message"]["content"].strip()
    return JSONResponse({"answer": answer, "catalog_count": len(catalog)})
