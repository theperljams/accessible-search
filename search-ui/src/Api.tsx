import axios from 'axios';

const API_URL = 'http://localhost:8000';

export const storeQueryAndResults = async (query: string, results: any[]) => {
  try {
    console.log(query, results);
    const response = await axios.post(`${API_URL}/store_query_and_results`, { query, results });
    return response.data;
  } catch (error) {
    console.error('Error storing query and results:', error);
    throw error;
  }
};