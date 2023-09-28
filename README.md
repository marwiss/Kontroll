# What is this

OpenCDE APIs Foundation API, BCF API, Documents API implemented in python, the FastAPI framework and the Neo4j graph database.

# Background

You can read some background information about the project here:

https://martin.wiss.se/data/bcf_ifc_graph.pdf

# Code structure

/docker-compose.yml
You bring up the project using this file.

/api/Dockerfile
Contains instructions for the FastAPI container.
Referenced by /docker-compose.yml

/api/app
Contains the server application.

/api/app/main.py
This is where the application starts.
The FastAPI-container will run this script on uvicorn.
main.py will load routes from scripts in the api folder.

/api/app/api
This is where the FastAPI routes are defined.

/api/app/repository
Routes often runs methods that will read or write data to or from a database.
This is where methods that read or write data from database are declared.

/api/app/database
Some general methods to interact with database.

/api/app/db_config
When the container is created it will initialize a database
with some test data from init.cypher. This initial state does not represent
all data. Model.cypher contains a more complete model.

/api/app/ifcgraph
Script to import data from IFC STEP file to Neo4j.

/api/app/models
Pydantic models used to define the JSON structures of requests and responses.
Models are arranged in files depending on if it is request or response
or both (common) or not at all (other).

/api/app/security
Contains methods for OAuth2 and a method to obtains secrets used.
You need to create your own secrets ad put them in the /secrets folder.

/api/app/templets
Jinja2 templates used to generate some webpages necessary for OAuth2 flow and Documents API flow.

/api/app/requirements.txt
Generated using pipreqs not pip freeze.

# Deployment

To get this code running you need:

- your own server
- a domain name
- a TLS-certificate for your domain name
- a proxy server
- to set up your proxy server to use HTTPS
- Docker
- to edit your .env file
- to create secrets and put them in the /secrets folder

# License

https://www.gnu.org/licenses/agpl-3.0.en.html

See the /LICENSE file.