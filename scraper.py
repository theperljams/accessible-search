import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc
from openai import OpenAI
import asyncio
import dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your client's origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("Starting FastAPI app")

import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
logger.info("Initializing OpenAI API")


def summarize_text(text):

    client = OpenAI()

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Summarize the following webpage content in three sentences."},
            {"role": "user", "content": text}
        ]
    )

    return completion.choices[0].message.content


def get_search_results_selenium(query):
    logger.info("Starting search for query: %s", query)
    driver = uc.Chrome()
    print("driver", driver)
    driver.get("https://www.google.com")

    # Search for the query
    search_box = driver.find_element(By.NAME, "q")
    print("search_box", search_box)
    search_box.send_keys(query)
    search_box.send_keys(Keys.RETURN)
    
    # Wait for results to load
    driver.implicitly_wait(2)
    
    results = []
    for result in driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc"):
        title_element = result.find_element(By.TAG_NAME, "h3")
        link_element = result.find_element(By.CSS_SELECTOR, "a")
        
        title = title_element.text
        link = link_element.get_attribute("href")
        logger.info("Found result: %s", result.text)
        
        # Summarize the webpage content
        summary = summarize_text(link)
        
        results.append({"title": title, "link": link, "summary": summary})
        logger.info("Found result: %s", title)
        
    driver.quit()
    logger.info("Search completed for query: %s", query)
    print(results)
    return results

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected")
    try:
        while True:
            query = await websocket.receive_text()
            logger.info("Received query from websocket: %s", query)
            results = get_search_results_selenium(query)
            
            for result in results:
                await websocket.send_json(result)
                user_response = await websocket.receive_text()
                if user_response.lower() == "yes":
                    logger.info("User found what they need, stopping results.")
                    break  # Stop sending more results if user found what they need
    except WebSocketDisconnect:
        logger.info("Client disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
