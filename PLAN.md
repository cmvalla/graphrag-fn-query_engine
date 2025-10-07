# PLAN.md for query-engine

## Objective: Perform Embedding Generation and Vector Search in a Single Spanner Query

The user wants to generate the query embedding and perform the vector search within a single Spanner query, removing the need for separate calls to an embedding service or generating the embedding in the Python code. This will be achieved by using Spanner's `ML.PREDICT` function with a registered Vertex AI embedding model.

### 1. Prerequisites: Registering a Vertex AI model in Spanner

This plan assumes that a Vertex AI embedding model (e.g., `textembedding-gecko`) is already deployed on a Vertex AI endpoint and registered within Spanner using `CREATE MODEL`. If not, this needs to be done first. The user will be responsible for this step.

The DDL for registering the model would look something like this:

```sql
CREATE MODEL EmbeddingsModel
INPUT(content STRING)
OUTPUT(embeddings ARRAY<FLOAT64>)
REMOTE OPTIONS (
  endpoint = '//aiplatform.googleapis.com/v1/projects/your-project/locations/us-central1/endpoints/your-endpoint'
);
```

### 2. Update the Spanner Query to use `ML.PREDICT`

I will modify the Spanner query in `functions/query-engine/main.py` to use `ML.PREDICT` to generate the embedding for the user's query and then use that embedding to find the most similar entities.

The new query will look like this:

```sql
WITH UserQueryEmbedding AS (
    SELECT embeddings[0] AS embedding
    FROM ML.PREDICT(
        MODEL EmbeddingsModel,
        (SELECT @query AS content)
    )
)
SELECT
    n.Eid AS id,
    n.Type AS type,
    n.Properties,
    n.Embedding,
    COSINE_DISTANCE(n.Embedding, (SELECT embedding FROM UserQueryEmbedding)) as distance
FROM
    Entities n
WHERE
    n.Embedding IS NOT NULL
UNION ALL
SELECT
    c.CommunityId AS id,
    'Community' AS type,
    PARSE_JSON(CONCAT('{"summary": "', c.Summary, '"}')) AS properties,
    c.Embedding,
    COSINE_DISTANCE(c.Embedding, (SELECT embedding FROM UserQueryEmbedding)) as distance
FROM
    Communities c
WHERE
    c.Embedding IS NOT NULL
ORDER BY
    distance
LIMIT @top_n
```

This query uses a Common Table Expression (CTE) `UserQueryEmbedding` to first generate the embedding for the user's query (`@query`) using the `EmbeddingsModel`. Then, it uses this embedding to calculate the `COSINE_DISTANCE`.

### 3. Update Python Code

-   **Remove `get_query_embedding` function:** This function will be removed.
-   **Remove `VertexAIEmbeddings` client:** The `VertexAIEmbeddings` client will no longer be needed.
-   **Update `query_engine` function:** The `query_engine` function will be simplified. It will only need to execute the new Spanner query, passing the user's `query` text and `top_n` as parameters. The embedding generation will be handled entirely within Spanner.
-   **LLM Call for final answer:** The logic for generating the final answer from the top N results using an LLM call will be kept for now. A future iteration could integrate this LLM call into the Spanner query as well, using another `ML.PREDICT` call with an `LLMModel`.
