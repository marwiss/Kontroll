# Kontroll BCF API server - OpenCDE APIs

## What is this

OpenCDE APIs:
Foundation API,
BCF API,
Documents API
implemented in python,
the FastAPI framework
and the Neo4j graph database.

## Background

You can read some background information about the project here:

https://martin.wiss.se/data/bcf_ifc_graph.pdf

## Code structure

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
Contains methods for OAuth2 and a method to get the secrets used.
You need to create your own secrets and put them in the /secrets folder.
Secrets are more secure than environment values.

/api/app/templets
Jinja2 templates used to generate some webpages necessary for OAuth2 flow and Documents API flow.

/api/app/requirements.txt
Generated using pipreqs not pip freeze.

## Deployment

To get this code running properly you need:

- your own server
- a domain name
- a TLS-certificate for your domain name
- a proxy server
- to set up your proxy server to use HTTPS
- Docker
- to edit your .env file with values specific for your server and API
- to create secrets and put them in the /secrets folder
- to put apoc-5.7.0-core and extended jars in /neo4j/plugins folder
- to put an ifcopenshell.zip in /api/app/ifcopenshell folder
- a BCF client, registered with client ID and secret

## TODO

This intention of this code was just to create a prototype for personal use.
Improvements are needed to collaborate on this code or to deploy this system in production.

Suggested improvements:

- General code structure refactoring
- Better commenting
- Testing scripts, unit testing
- Better error handling
- More consistent logging
- Easier deployment
- User registration and admin system
- BCF client registration functionality
- OData to CYPHER converter
- Documents API and BCF API integration
- More complete OpenAPI documentation of routes
- More complete documentation of pydantic models
- Improvements on IFC-graph
- Replace hard coded values with .env values
- Improve security before deployment in production

## Prototype

This code was developed and tested on a system using:

- Ubuntu 20
- Nginx 1.18
- Lets encrypt, certbot
- Docker 20

## Suggested reading

### FastAPI

- FastAPI documentation
  https://fastapi.tiangolo.com/

- Building Python Microservices with FastAPI
  https://www.packtpub.com/product/building-python-microservices-with-fastapi/9781803245966

- Building Python Web APIs with FastAPI
  https://www.packtpub.com/product/building-python-web-apis-with-fastapi/9781801076630

- Building Data Science Applications with FastAPI - Second Edition
  https://www.packtpub.com/product/building-data-science-applications-with-fastapi-second-edition/9781837632749

### OAuth2

- Mastering OAuth 2.0
https://www.packtpub.com/product/mastering-oauth-20/9781784395407

- OAuth 2.0 Cookbook
https://www.packtpub.com/product/oauth-20-cookbook/9781788295963

### Neo4j and cypher

- Neo4j Cypher Manual
https://neo4j.com/docs/cypher-manual/current/introduction/

- Using Neo4j from python
https://neo4j.com/docs/getting-started/languages-guides/neo4j-python/

### OpenCDE APIs

- BCF REST API
https://github.com/buildingSMART/BCF-API

- Documents API
https://github.com/buildingSMART/documents-API

- Foundation API
https://github.com/buildingSMART/foundation-API

### Pydantic

- Pydantic docs
https://docs.pydantic.dev/latest/

### IFC-graph

- IFC-graph for facilitating building information access and query
https://www.sciencedirect.com/science/article/pii/S0926580523000389

### Docker

- Docker documentation
https://docs.docker.com/

### Nginx

- NGINX Reverse Proxy documentation
https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/

### Certbot

- Certbot documentation
https://eff-certbot.readthedocs.io/en/stable/

## License

The GNU Affero General Public License is a free,
copyleft license for software and other kinds of works,
specifically designed to ensure cooperation with the community
in the case of network server software.

https://www.gnu.org/licenses/agpl-3.0.en.html

See the /LICENSE file.