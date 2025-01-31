from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import openai
import asyncio
import dotenv

app = FastAPI()

import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def summarize_text(text):
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Summarize the following webpage content in three sentences."},
            {"role": "user", "content": text}
        ]
    )
    return response["choices"][0]["message"]["content"]

def get_search_results_selenium(query):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    driver = webdriver.Chrome(options=options)
    driver.get("https://www.google.com")

    # Search for the query
    search_box = driver.find_element(By.NAME, "q")
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
        
        # Summarize the webpage content
        summary = summarize_text(link)
        
        results.append({"title": title, "link": link, "summary": summary})
        
    driver.quit()
    return results

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            query = await websocket.receive_text()
            results = get_search_results_selenium(query)
            
            for result in results:
                await websocket.send_json(result)
                user_response = await websocket.receive_text()
                if user_response.lower() == "yes":
                    break  # Stop sending more results if user found what they need
    except WebSocketDisconnect:
        print("Client disconnected")
