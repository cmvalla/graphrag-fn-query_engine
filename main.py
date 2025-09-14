import os
import json
import functions_framework
import google.cloud.logging
import logging
from google.cloud import spanner
from langchain_google_vertexai import VertexAI
from langchain.prompts import PromptTemplate
import requests
import time

# --- Boilerplate and Configuration ---

# Setup structured logging
logging_client = google.cloud.logging.Client()
logging_client.setup_logging()
logging.basicConfig(level=logging.INFO)

# --- Global Clients (initialized within the function) ---
llm = None
spanner_database = None

initialize_clients() # Moved initialization here

def get_query_embedding(query: str):
    """Generates an embedding for a given query by calling the graphrag-embedding service."""
    embedding_service_url = os.environ.get("EMBEDDING_SERVICE_URL")
    if not embedding_service_url:
        logging.error("EMBEDDING_SERVICE_URL environment variable not set.")
        return None

    try:
        token_url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={embedding_service_url}"
        token_response = requests.get(token_url, headers={"Metadata-Flavor": "Google"})
        token = token_response.text
        headers = {"Authorization": f"Bearer {token}"}
        
        payload = {"text": query, "embedding_types": ["semantic_query"]}
        logging.info(f"Sending embedding request for query: {query}")
        response = requests.post(embedding_service_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            all_embeddings = response.json().get("embeddings")
            if all_embeddings and isinstance(all_embeddings, dict):
                return all_embeddings.get("semantic_query", [[]])[0]
            else:
                logging.warning(f"Embeddings not found or invalid in response for query: {query}. Full response: {response.text}")
                return None
        else:
            logging.error(f"Embedding service returned a client error ({response.status_code}) for query {query}: {response.text}")
            response.raise_for_status()
            return None

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling embedding service for query {query}: {e}")
        return None

def initialize_clients():
    """Initializes all external clients."""
    global llm, spanner_database

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
        query_embedding = get_query_embedding(query)
        if not query_embedding:
            return "Failed to generate query embedding", 500

        # 2. Fetch community summaries and embeddings from Spanner Graph
        # Assuming nodes (e.g., 'Community') have 'summary' and 'embedding' properties
        # and that 'embedding' is stored as an ARRAY<FLOAT64>
        # Example GQL query (adjust table/column names as per your Spanner Graph schema)
        # Fetch all entities (including Class, Instance, and Community) and their embeddings
        gql_query = """
        MATCH (n)
        RETURN n.id AS id, n.type AS type, n.properties AS properties, n.embedding AS embedding
        """
        
        graph = spanner_database.graph('my_graph') # Confirmed graph name from spanner.tf
        with graph.snapshot() as snapshot:
            results = snapshot.execute_sql(gql_query)
            all_entities_data = []
            for row in results:
                entity_id = row[0]
                entity_type = row[1]
                entity_properties = json.loads(row[2]) if row[2] else {} # Properties are JSON
                entity_embedding = list(row[3]) if row[3] else None # Embedding is ARRAY<FLOAT64>
                
                all_entities_data.append({
                    "id": entity_id,
                    "type": entity_type,
                    "properties": entity_properties,
                    "embedding": entity_embedding
                })

        # 3. Perform similarity search to find top N relevant entities (Class, Instance, Community)
        # Calculate cosine similarity between query embedding and entity embeddings
        from sklearn.metrics.pairwise import cosine_similarity # This will require adding sklearn to requirements.txt
        
        # Filter out entities without embeddings or with non-list embeddings
        valid_entities = []
        for entity in all_entities_data:
            if entity.get("embedding") and isinstance(entity["embedding"], list):
                valid_entities.append(entity)
            else:
                logging.warning(f"Entity {entity.get('id')} has invalid or missing embedding: {entity.get('embedding')}")

        if not valid_entities:
            logging.warning("No valid entity embeddings found for similarity search. Cannot perform semantic search.")
            return "No relevant information found.", 200 # Or handle as appropriate

        entity_embeddings = [entity["embedding"] for entity in valid_entities]
        
        # Reshape query_embedding for cosine_similarity
        query_embedding_reshaped = [query_embedding]
            
        similarities = cosine_similarity(query_embedding_reshaped, entity_embeddings)[0]

        # Get top N entities based on similarity
        top_n = 5 # Define top N entities to consider
        top_n_indices = similarities.argsort()[-top_n:][::-1]
        top_n_entities = [valid_entities[i] for i in top_n_indices]
        
        logging.info(f"Top {top_n} entities for query '{query}': {[entity['id'] for entity in top_n_entities]}")


        # 4. Generate partial answers for top N relevant entities
        partial_answers = []
        for entity in top_n_entities:
            entity_id = entity["id"]
            entity_type = entity["type"]
            entity_properties = entity["properties"]
            
            summary = ""
            if entity_type == "Community" or entity_type == "Class":
                summary = entity_properties.get("summary", "")
                if not summary:
                    logging.warning(f"Entity {entity_id} of type {entity_type} has no 'summary' property. Using full properties.")
                    summary = json.dumps(entity_properties)
            elif entity_type == "Instance":
                summary = entity_properties.get("name", entity_properties.get("description", ""))
                if not summary:
                    logging.warning(f"Entity {entity_id} of type {entity_type} has no 'name' or 'description' property. Using full properties.")
                    summary = json.dumps(entity_properties)
            else:
                logging.warning(f"Unknown entity type {entity_type} for entity {entity_id}. Using full properties.")
                summary = json.dumps(entity_properties)

            if not summary:
                logging.warning(f"No meaningful summary could be extracted for entity {entity_id}. Skipping partial answer generation for this entity.")
                continue

            prompt = PARTIAL_ANSWER_PROMPT.format(query=query, summary=summary)
            partial_answer = llm.invoke(prompt)
            partial_answers.append(partial_answer)

        # 5. Generate final answer
        if not partial_answers:
            logging.warning("No partial answers generated. Returning default response.")
            return "No relevant information found to answer your query.", 200

        partial_answers_str = "\n".join(partial_answers)
        prompt = FINAL_ANSWER_PROMPT.format(query=query, partial_answers=partial_answers_str)
        final_answer = llm.invoke(prompt)

        return final_answer, 200

    except Exception as e:
        logging.error(f'An error occurred in the query engine: {e}', exc_info=True)
        return "Internal Server Error", 500