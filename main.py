import os
import json
import functions_framework
import google.cloud.logging
import logging
from google.cloud import spanner
from langchain_google_vertexai import VertexAI, VertexAIEmbeddings
from langchain.prompts import PromptTemplate

# --- Boilerplate and Configuration ---

# Setup structured logging
logging_client = google.cloud.logging.Client()
logging_client.setup_logging()
logging.basicConfig(level=logging.INFO)

# --- Global Clients (initialized within the function) ---
llm = None
spanner_database = None
embedding_model = None # New global variable for embedding model

def initialize_clients():
    """Initializes all external clients."""
    global llm, spanner_database, embedding_model # Update global variables

    try:
        logging.info("Initializing global clients...")

        # --- Environment Variables ---
        GCP_PROJECT = os.environ.get("GCP_PROJECT")
        SPANNER_INSTANCE_ID = os.environ.get("SPANNER_INSTANCE_ID")
        SPANNER_DATABASE_ID = os.environ.get("SPANNER_DATABASE_ID")
        LOCATION = os.environ.get("LOCATION")

        logging.info("Initializing Cloud Spanner client...")
        spanner_client = spanner.Client(project=GCP_PROJECT)
        instance = spanner_client.instance(SPANNER_INSTANCE_ID)
        spanner_database = instance.database(SPANNER_DATABASE_ID)
        logging.info("Cloud Spanner client initialized successfully.")

        logging.info("Initializing Vertex AI...")
        llm = VertexAI(model_name="gemini-2.5-flash", location=LOCATION)
        logging.info("Vertex AI LLM client initialized successfully.")

        # Initialize Vertex AI Embeddings
        embedding_model = VertexAIEmbeddings(model_name="text-embedding-004", location=LOCATION) # Using a common embedding model
        logging.info("Vertex AI Embeddings client initialized successfully.")

        logging.info("All global clients initialized successfully.")
    except Exception as e:
        logging.critical(f'FATAL: Failed to initialize one or more global clients: {e}', exc_info=True)
        raise  # Re-raise the exception to halt execution if initialization fails

# --- Prompt Templates ---
PARTIAL_ANSWER_PROMPT = PromptTemplate(
    input_variables=["query", "summary"],
    template="""
    Given the following query and summary, please provide a partial answer to the query based on the summary.

    Query: {query}

    Summary: {summary}

    Partial Answer:
    """
)

FINAL_ANSWER_PROMPT = PromptTemplate(
    input_variables=["query", "partial_answers"],
    template="""
    Given the following query and partial answers, please provide a final global answer.

    Query: {query}

    Partial Answers:
    {partial_answers}

    Final Answer:
    """
)

@functions_framework.http
def query_engine(request):
    """
    Answers a global sensemaking query using the community summaries from Spanner Graph.
    """
    try:
        initialize_clients()

        request_json = request.get_json(silent=True)
        if not request_json or "query" not in request_json:
            return "Bad Request: Invalid JSON or missing query", 400

        query = request_json["query"]

        # 1. Generate embedding for the user query
        query_embedding = embedding_model.embed_query(query)

        # 2. Fetch community summaries and embeddings from Spanner Graph
        # Assuming nodes (e.g., 'Community') have 'summary' and 'embedding' properties
        # and that 'embedding' is stored as an ARRAY<FLOAT64>
        # Example GQL query (adjust table/column names as per your Spanner Graph schema)
        gql_query = """
        MATCH (c:Community)
        RETURN c.id AS community_id, c.summary AS summary, c.embedding AS embedding
        """
        
        graph = spanner_database.graph('my-graph')
        with graph.snapshot() as snapshot:
            results = snapshot.execute_sql(gql_query)
            communities_data = []
            for row in results:
                communities_data.append({
                    "community_id": row[0],
                    "summary": row[1],
                    "embedding": list(row[2]) # Convert Spanner ARRAY to Python list
                })

        # 3. Perform similarity search to find top N relevant communities
        # Calculate cosine similarity between query embedding and community embeddings
        from sklearn.metrics.pairwise import cosine_similarity # This will require adding sklearn to requirements.txt
        
        # Filter out communities without embeddings or with non-list embeddings
        valid_communities = []
        for comm in communities_data:
            if comm.get("embedding") and isinstance(comm["embedding"], list):
                valid_communities.append(comm)
            else:
                logging.warning(f"Community {comm.get('community_id')} has invalid or missing embedding: {comm.get('embedding')}")

        if not valid_communities:
            logging.warning("No valid community embeddings found for similarity search. Proceeding with all summaries.")
            # Fallback to using all summaries if no valid embeddings are found
            top_n_communities = communities_data
        else:
            community_embeddings = [comm["embedding"] for comm in valid_communities]
            
            # Reshape query_embedding for cosine_similarity
            query_embedding_reshaped = [query_embedding]
            
            similarities = cosine_similarity(query_embedding_reshaped, community_embeddings)[0]

            # Get top N communities based on similarity
            top_n = 5 # Define top N communities to consider
            top_n_indices = similarities.argsort()[-top_n:][::-1]
            top_n_communities = [valid_communities[i] for i in top_n_indices]
            
            logging.info(f"Top {top_n} communities for query '{query}': {[comm['community_id'] for comm in top_n_communities]}")


        # 4. Generate partial answers for top N relevant communities
        partial_answers = []
        for record in top_n_communities:
            community_id = record["community_id"]
            summary = record["summary"]
            prompt = PARTIAL_ANSWER_PROMPT.format(query=query, summary=summary)
            partial_answer = llm.invoke(prompt)
            partial_answers.append(partial_answer)

        # 3. Generate final answer
        partial_answers_str = "\n".join(partial_answers)
        prompt = FINAL_ANSWER_PROMPT.format(query=query, partial_answers=partial_answers_str)
        final_answer = llm.invoke(prompt)

        return final_answer, 200

    except Exception as e:
        logging.error(f'An error occurred in the query engine: {e}', exc_info=True)
        return "Internal Server Error", 500
