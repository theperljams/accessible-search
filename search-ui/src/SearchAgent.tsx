import React, { useState, useEffect } from "react";
import "./SearchAgent.css"; // Import the new stylesheet
import { storeResult } from "./Api"; // Import the API utility

type SearchResult = {
  id: string;
  title: string;
  summary: string;
  link: string;
};

const SearchAgent: React.FC = () => {
  const [query, setQuery] = useState<string>("");
  const [currentResults, setCurrentResults] = useState<SearchResult[]>([]);
  const [resultQueue, setResultQueue] = useState<SearchResult[]>([]);
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws");

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.suggestions) {
        setSuggestions(data.suggestions);
      } else if (data.results) {
        const results: SearchResult[] = data.results;
        setResultQueue((prevQueue) => [...prevQueue, ...results]);
        setIsLoading(false); // Stop loading when results are received
      }
    };

    setSocket(ws);
    return () => {
      ws.close();
    };
  }, []);

  const sendQuery = () => {
    if (socket && query.trim()) {
      setCurrentResults([]);
      setResultQueue([]);
      setIsLoading(true); // Start loading when query is sent
      socket.send(JSON.stringify({ query }));
    }
  };

  const handleResponse = async (response: string) => {
    if (socket) {
      if (response.toLowerCase() === "yes") {
        for (const result of currentResults) {
          await storeResult(result);
        }
        socket.send(response);
        socket.close();
      } else {
        // User wants more results
        if (resultQueue.length > 0) {
          // Display next 3 from already fetched
          setCurrentResults(resultQueue.slice(0, 3));
          setResultQueue(resultQueue.slice(3));
        } else {
          // Ask server for more
          setIsLoading(true); // Start loading when requesting more results
          socket.send("more");
        }
      }
    }
  };

  // When new results arrive, stop loading and show them if none are displayed
  useEffect(() => {
    if (resultQueue.length > 0 && currentResults.length === 0) {
      setIsLoading(false);
      setCurrentResults(resultQueue.slice(0, 3));
      setResultQueue(resultQueue.slice(3));
    }
  }, [resultQueue, currentResults]);

  const handleKeyPress = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      if (socket && query.trim()) {
        // Request suggestions when user presses Enter
        socket.send(JSON.stringify({ suggest: query.trim() }));
      }
    }
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    // Only update local state here, no suggestions request
    setQuery(event.target.value);
  };

  const handleResultClick = async (result: SearchResult) => {
    await storeResult(result);
  };

  return (
    <div className="search-agent-container">
      <h1 className="search-agent-title">Search Agent</h1>
      <input
        className="search-input"
        type="text"
        value={query}
        onChange={handleInputChange}
        onKeyPress={handleKeyPress}
        placeholder="Enter your search query"
      />
      <button className="search-button" onClick={sendQuery}>Search</button>
      <div className="suggestions-container">
        {suggestions.map((suggestion, index) => (
          <div key={index} className="suggestion-item" onClick={() => setQuery(suggestion)}>
            {suggestion}
          </div>
        ))}
      </div>
      <div className="results-container">
        {currentResults.map((result, index) => (
          <div className="result-item" key={index} onClick={() => handleResultClick(result)}>
            <h3>{result.title}</h3>
            <p>{result.summary}</p>
            <a href={result.link} target="_blank" rel="noopener noreferrer">
              Read more
            </a>
          </div>
        ))}
      </div>

      {isLoading && (
        <div className="loading-indicator">
          Loading next results...
        </div>
      )}

      <div className="control-buttons">
        <button className="control-button" onClick={() => handleResponse("yes")}>
          Yes, this is useful
        </button>
        <button className="control-button" onClick={() => handleResponse("more")}>
          Next results
        </button>
      </div>
    </div>
  );
};

export default SearchAgent;
