# Query Engine - Functional Analysis

The query engine is a Flask application that exposes a single endpoint `/` to answer questions.

## Endpoint

- **URL**: `/`
- **Method**: `POST`
- **Request Body**:
  ```json
  {
    "query": "Your question here"
  }
  ```
- **Response Body**:
  ```json
  {
    "answer": "The answer to your question"
  }
  ```

## Workflow

The query engine follows these steps to answer a question:

1.  **Get the query from the request:**
    - It gets the JSON payload from the request.
    - It checks if the payload is valid and if it contains a "query" field.
    - If not, it returns a 400 Bad Request error.

2.  **Generate an embedding for the user query:**
    - It calls the `get_query_embedding` function to generate an embedding for the user's query.
    - The `get_query_embedding` function calls an external service (the `graphrag-embedding` service) to generate the embedding.
    - If the embedding generation fails, it returns a 500 Internal Server Error.

3.  **Fetch entities and embeddings from Spanner Graph:**
    - It defines a GQL query to fetch all entities from the graph.
    - It creates a snapshot of the Spanner database.
    - It creates an `ExecuteSqlRequest` object with the GQL query and sets the `query_mode` to `QueryMode.PLAN`.
    - It executes the query using `snapshot.execute_sql(request)`.
    - It iterates over the results and creates a list of dictionaries, where each dictionary represents an entity with its ID, type, properties, and embedding.

4.  **Perform similarity search:**
    - It uses the `cosine_similarity` function from `scikit-learn` to calculate the similarity between the user's query embedding and the embeddings of all the entities in the graph.
    - It filters out entities that don't have an embedding.
    - It gets the top 5 most similar entities.

5.  **Generate partial answers:**
    - It iterates over the top 5 entities.
    - For each entity, it extracts a summary from its properties.
    - It uses a prompt template (`PARTIAL_ANSWER_PROMPT`) to ask the LLM to generate a partial answer to the user's query based on the entity's summary.
    - It collects all the partial answers.

6.  **Generate final answer:**
    - It uses another prompt template (`FINAL_ANSWER_PROMPT`) to ask the LLM to generate a final answer based on the user's query and the partial answers.
    - It returns the final answer as a JSON response.

## Helper Functions

- **`initialize_clients()`**: This function is called when the application starts. It initializes the Spanner and Vertex AI clients.
- **`get_query_embedding(query: str)`**: This function is responsible for calling the `graphrag-embedding` service to get the embedding for the query. It handles authentication by getting an identity token from the metadata server.
