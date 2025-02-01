import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc
from openai import OpenAI
import os
from dotenv import load_dotenv
import json  # Add this import

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

def classify_text(text, filters):
    client = OpenAI()
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"Classify the following text into one of the categories: {', '.join(filters)}. An opinion is any sort of online forum, reddit/social media platforms, or blog. A fact is something like wikipedia, or any sort of website that is made to provide trivia type facts or tutorials."},
            {"role": "user", "content": text}
        ]
    )
    return completion.choices[0].message.content.lower()

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

def parse_results(driver, filters):
    driver.implicitly_wait(2)
    new_results = []
    search_results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc")
    logger.info("Number of search results found: %d", len(search_results))

    for item in search_results:
        try:
            title_el = item.find_element(By.TAG_NAME, "h3")
            link_el = item.find_element(By.CSS_SELECTOR, "a")
            title = title_el.text
            link = link_el.get_attribute("href")
            summary = summarize_text(link)
            if "research" not in filters:
                classification = classify_text(summary, filters)
                if classification in filters:
                    new_results.append(SearchResult(title, link, summary))
        except Exception as e:
            logger.error("Error processing result: %s", e)

    return new_results

def click_next_page(driver):
    # Scroll to bottom before finding "Next" link
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    driver.implicitly_wait(1)
    try:
        next_button = driver.find_element(By.ID, "pnnext")
        next_button.click()
        return True
    except Exception as e:
        logger.info("No more pages to load: %s", e)
        return False

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected")
    try:
        driver = None
        results_queue = []
        while True:
            if not driver:
                data = await websocket.receive_text()
                data = json.loads(data)
                query = data["query"]
                filters = [key for key, value in data["filters"].items() if value]
                logger.info("Received query from websocket: %s", query)
                driver = uc.Chrome()
                if "research" in filters:
                    driver.get("https://scholar.google.com")
                else:
                    driver.get("https://www.google.com")
                search_box = driver.find_element(By.NAME, "q")
                search_box.send_keys(query)
                search_box.send_keys(Keys.RETURN)
                results_queue = parse_results(driver, filters)

            # Send results three at a time
            while len(results_queue) > 0:
                chunk = results_queue[:3]
                results_queue = results_queue[3:]
                logger.info("Sending 3-result chunk to client.")
                await websocket.send_json([r.to_dict() for r in chunk])

                user_response = await websocket.receive_text()
                if user_response.lower() == "yes":
                    logger.info("User found what they need, stopping.")
                    driver.quit()
                    return
                elif user_response.lower() == "more":
                    logger.info("User wants more information.")
                    continue
                # If user says something else, continue sending the next chunk

            # If queue is empty and user still wants more, try next page
            logger.info("No more results on this page.")
            await websocket.send_json([{"info": "No more results on this page."}])
            user_response = await websocket.receive_text()
            if user_response.lower() == "yes":
                logger.info("User found what they need, stopping.")
                driver.quit()
                return
            elif user_response.lower() == "more":
                # Click next
                if click_next_page(driver):
                    logger.info("Loading next page")
                    results_queue = parse_results(driver, filters)
                    continue
                else:
                    logger.info("No further pages available.")
                    driver.quit()
                    return
    except WebSocketDisconnect:
        logger.info("Client disconnected")
        if driver:
            driver.quit()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
