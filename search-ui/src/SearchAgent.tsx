import React, { useState, useEffect } from "react";

type SearchResult = {
    title: string;
    summary: string;
    link: string;
};

const SearchAgent: React.FC = () => {
    const [query, setQuery] = useState<string>("");
    const [currentResults, setCurrentResults] = useState<SearchResult[]>([]);
    const [resultQueue, setResultQueue] = useState<SearchResult[]>([]);
    const [socket, setSocket] = useState<WebSocket | null>(null);
    
    useEffect(() => {
        const ws = new WebSocket("ws://localhost:8000/ws");
        ws.onmessage = (event) => {
            const results: SearchResult[] = JSON.parse(event.data);
            setResultQueue((prevQueue) => [...prevQueue, ...results]);
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
            socket.send(query);
        }
    };

    const handleResponse = (response: string) => {
        if (socket) {
            if (response.toLowerCase() === "yes") {
                socket.send(response);
                socket.close();
            } else {
                if (resultQueue.length > 0) {
                    setCurrentResults(resultQueue.slice(0, 2));
                    setResultQueue(resultQueue.slice(2));
                } else {
                    socket.send("more");
                }
            }
        }
    };

    useEffect(() => {
        if (resultQueue.length > 0 && currentResults.length === 0) {
            setCurrentResults(resultQueue.slice(0, 2));
            setResultQueue(resultQueue.slice(2));
        }
    }, [resultQueue, currentResults]);

    return (
        <div>
            <h1>Search Agent</h1>
            <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Enter your search query"
            />
            <button onClick={sendQuery}>Search</button>
            <div>
                {currentResults.map((result, index) => (
                    <div key={index}>
                        <h3>{result.title}</h3>
                        <p>{result.summary}</p>
                        <a href={result.link} target="_blank" rel="noopener noreferrer">Read more</a>
                    </div>
                ))}
                {currentResults.length > 0 && (
                    <div>
                        <button onClick={() => handleResponse("yes")}>Yes, this is useful</button>
                        <button onClick={() => handleResponse("no")}>Next results</button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default SearchAgent;
