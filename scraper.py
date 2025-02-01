import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc
from openai import OpenAI
import os
from dotenv import load_dotenv
import json
import supabase
import uuid
import re
from pydantic import BaseModel
from typing import List, Dict

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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client = supabase.create_client(SUPABASE_URL, SUPABASE_KEY)

logger.info("Initializing OpenAI API")

# These are all synchronous because they call blocking code directly
def summarize_text(text: str) -> str:
    client = OpenAI()
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Summarize the following webpage content in three sentences."},
            {"role": "user", "content": text}
        ]
    )
    return completion.choices[0].message.content

def embed_text(text: str):
    client = OpenAI()

    response = client.embeddings.create(
        input=text,
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def get_all_searches():
    response = supabase_client.table('search_results').select('*').execute()
    return response.data

def match_search_results(query_embedding, similarity_threshold: float, match_count: int):
    response = supabase_client.rpc(
        "match_search_results",
        {
            "query_embedding": query_embedding,
            "similarity_threshold": similarity_threshold,
            "match_count": match_count
        }
    ).execute()
    result = response.data
    logger.info("Matched search results: %s", result)
    return result

def has_numerical_character(input_string: str) -> bool:
    return bool(re.search(r'\d', input_string))

def parse_numbered_list(input_string: str) -> list:
    lines = input_string.strip().split('\n')
    items = []

    for line in lines:
        parts = line.split('. ', 1)
        if len(parts) == 2 and parts[0].isdigit():
            item_content = parts[1].strip()
            items.append(item_content)

    return items

def suggest_searches(query: str):
    client = OpenAI()
    relevant_searches = match_search_results(embed_text(query), 0.4, 10)
    logger.info("Relevant searches: %s", relevant_searches)

    prompt = f'''Below are some samples of the user's search history. Given the first word that the user types, I want you to suggest
    what the user most likely wants to search for. For example, do the results contain a lot of reddit searches? Wikipedia? Factoids?
    Does the user prefer tutorials? Suggest a google search that is the most likely to get the user what they want based on their search history.
    Here are the user's last few searches and results:

    {relevant_searches}

    And here is the current search: {query}

    Give me a numbered list of 3 potential searches. No quotation marks.
    '''

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": query}
        ]
    )
    result = completion.choices[0].message.content
    search_queries = parse_numbered_list(result)
    logger.info("Suggested searches: %s", search_queries)
    return search_queries

class SearchResult:
    def __init__(self, title, link, summary):
        self.id = str(uuid.uuid4())
        self.title = title
        self.link = link
        self.summary = summary

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "link": self.link,
            "summary": self.summary
        }

def parse_results(driver) -> list:
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
            new_results.append(SearchResult(title, link, summary))
        except Exception as e:
            logger.error("Error processing result: %s", e)

    return new_results

def click_next_page(driver) -> bool:
    # Scroll to bottom before finding "Next" link
    logger.info("Scrolling to bottom of page/clicking next")
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    driver.implicitly_wait(1)
    try:
        next_button = driver.find_element(By.ID, "pnnext")
        next_button.click()
        return True
    except Exception as e:
        logger.info("No more pages to load: %s", e)
        return False

# This route must remain async because websockets in FastAPI are async
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected")
    try:
        driver = None
        results_queue = []

        while True:
            data = await websocket.receive_text()
            if not data:
                logger.error("Received empty data from websocket")
                continue

            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error("Error decoding JSON: %s", e)
                continue

            if "suggest" in data:
                suggestions = suggest_searches(data["suggest"])
                await websocket.send_json({"suggestions": suggestions})
                continue

            query = data["query"]
            logger.info("Received query from websocket: %s", query)
            driver = uc.Chrome()
            driver.get("https://www.google.com")
            search_box = driver.find_element(By.NAME, "q")
            search_box.send_keys(query)
            search_box.send_keys(Keys.RETURN)
            results_queue = parse_results(driver)

            end_response = ''

            # Send results three at a time
            while len(results_queue) > 0:
                chunk = results_queue[:3]
                logger.info("Chunk: %s", chunk)
                results_queue = results_queue[3:]
                logger.info("queue: %s", results_queue)
                logger.info("Sending 3-result chunk to client.")
                await websocket.send_json({"results": [r.to_dict() for r in chunk]})

                user_response = await websocket.receive_text()
                logger.info("User response: %s", user_response)
                if user_response.lower() == "yes":
                    logger.info("User found what they need, stopping.")
                    driver.quit()
                    return
                elif user_response.lower() == "more":
                    logger.info("User wants more information.")
                    if len(results_queue) == 0:
                        end_response = "more"
                    continue

            logger.info("end_response: %s", end_response)
                # If user says something else, continue sending the next chunk

            # If queue is empty and user still wants more, try next page
            if end_response.lower() == "yes":
                logger.info("User found what they need, stopping.")
                driver.quit()
                return
            elif end_response.lower() == "more":
                # Click next
                if click_next_page(driver):
                    logger.info("Loading next page")
                    results_queue = parse_results(driver)
                    # Send results three at a time
                    while len(results_queue) > 0:
                        chunk = results_queue[:3]
                        results_queue = results_queue[3:]
                        logger.info("Sending 3-result chunk to client.")
                        await websocket.send_json({"results": [r.to_dict() for r in chunk]})

                        user_response = await websocket.receive_text()
                        if user_response.lower() == "yes":
                            logger.info("User found what they need, stopping.")
                            driver.quit()
                            return
                        elif user_response.lower() == "more":
                            logger.info("User wants more information.")
                            continue
                        # If user says something else, continue sending the next chunk
                else:
                    logger.info("No further pages available.")
                    driver.quit()
                    return
    except WebSocketDisconnect:
        logger.info("Client disconnected")
        if driver:
            driver.quit()

class QueryResults(BaseModel):
    query: str
    results: List[Dict]

@app.post("/store_query_and_results")
def store_query_and_results(payload: QueryResults):
    query = payload.query
    results = payload.results

    for result in results:
        logger.info("Storing search result: %s", result)
        result["embedding"] = embed_text(result["summary"])
        result["query"] = query
        supabase_client.table("search_results").insert(result).execute()
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
