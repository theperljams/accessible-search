import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc
from openai import OpenAI
import os
from dotenv import load_dotenv

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

class SearchResult:
    def __init__(self, title, link, summary):
        self.title = title
        self.link = link
        self.summary = summary

    def to_dict(self):
        return {
            "title": self.title,
            "link": self.link,
            "summary": self.summary
        }

def get_search_results_selenium(query, start=0):
    logger.info("Starting search for query: %s", query)
    driver = uc.Chrome()
    driver.get("https://www.google.com")

    # Search for the query
    search_box = driver.find_element(By.NAME, "q")
    search_box.send_keys(query)
    search_box.send_keys(Keys.RETURN)
    
    # Wait for results to load
    driver.implicitly_wait(2)
    
    results = []
    search_results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc")
    logger.info("Number of search results found: %d", len(search_results))
    
    for result in search_results[start:start+10]:  # Fetch 10 results at a time
        try:
            title_element = result.find_element(By.TAG_NAME, "h3")
            link_element = result.find_element(By.CSS_SELECTOR, "a")
            
            title = title_element.text
            link = link_element.get_attribute("href")
            logger.info("Found result: %s", title)
            
            # Summarize the webpage content
            summary = summarize_text(link)
            
            results.append(SearchResult(title, link, summary))
            logger.info("Added result: %s", title)
        except Exception as e:
            logger.error("Error processing result: %s", e)
        
    driver.quit()
    logger.info("Search completed for query: %s", query)
    return results

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected")
    try:
        query = None
        start = 0
        while True:
            if query is None:
                query = await websocket.receive_text()
                logger.info("Received query from websocket: %s", query)
            
            results = get_search_results_selenium(query, start)
            if not results:
                break
            
            for i in range(0, len(results), 2):
                batch = results[i:i+2]
                await websocket.send_json([result.to_dict() for result in batch])
                user_response = await websocket.receive_text()
                if user_response.lower() == "yes":
                    logger.info("User found what they need, stopping results.")
                    return  # Stop sending more results if user found what they need
                elif user_response.lower() == "more":
                    start += 10  # Move to the next set of results
                    break  # Exit the inner loop to fetch more results
    except WebSocketDisconnect:
        logger.info("Client disconnected")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
