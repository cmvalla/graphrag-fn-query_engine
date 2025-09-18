import pytest
from main import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_query_engine_integration(client):
    # Send a request to the query engine
    response = client.post('/', json={'query': 'chi è il lupo'})

    # Check the response
    assert response.status_code == 200
    assert 'answer' in response.json