import React, { useState, useEffect } from "react";

type SearchResult = {
    title: string;
    summary: string;
    link: string;
};

const SearchAgent: React.FC = () => {
    const [query, setQuery] = useState<string>("");
    const [currentResult, setCurrentResult] = useState<SearchResult | null>(null);
    const [socket, setSocket] = useState<WebSocket | null>(null);
    
    useEffect(() => {
        const ws = new WebSocket("ws://localhost:8000/ws");
        ws.onmessage = (event) => {
            const result: SearchResult = JSON.parse(event.data);
            setCurrentResult(result);
        };
        setSocket(ws);

        return () => {
            ws.close();
        };
    }, []);

    const sendQuery = () => {
        if (socket && query.trim()) {
            setCurrentResult(null);
            socket.send(query);
        }
    };

    const handleResponse = (response: string) => {
        if (socket) {
            socket.send(response);
            if (response.toLowerCase() === "yes") {
                socket.close();
            }
        }
    };

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
                {currentResult && (
                    <div>
                        <h3>{currentResult.title}</h3>
                        <p>{currentResult.summary}</p>
                        <a href={currentResult.link} target="_blank" rel="noopener noreferrer">Read more</a>
                        <div>
                            <button onClick={() => handleResponse("yes")}>Yes, this is useful</button>
                            <button onClick={() => handleResponse("no")}>Next result</button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default SearchAgent;
