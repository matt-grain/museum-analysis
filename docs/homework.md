## IVADO LABS Homework

A new world organization has just been created. 
It includes all the museum management committees that have more than 2,000,000 visitors annually.  
This list is available via Wikipedia: https://en.wikipedia.org/wiki/List_of_most_visited_museums

This new organization wishes to correlate the tourist attendance at their museums with the population of the respective cities. 
To achieve this, a small, common and harmonized database must be built to be able to extract features. 
This DB must include the characteristics of museums as well as the population of the cities in which they are located. You have been chosen to build this database. 
In addition, you are asked to create a small linear regression ML algorithm to correlate the city population and the influx of visitors.  

Your solution must balance the need for quickly assessing the data, rapid prototyping and deploying a MVP to a (potentially) public user that could later scale. 
You must use the Wikipedia APIs to retrieve this list of museums and their characteristics. 
You are free to choose the source of your choice for the population of the cities concerned.

Deliverables:
1. It is required that your code is a structured Python project. The code should be packaged and exposed in a Docker container (use Docker Compose if you require additional infrastructure).

2. A jupyter notebook hosted in docker should also be created. This notebook should  programmatically use your other code to visually present the results of your regression model.

You will be evaluated not only on how your code works but also on the rationale for the choices you make. 

## Matt's analysis - to be challenged

Target: docker compose with containers:
- database to store raw data: museums and associated characteristics, cities with population where museums are located
- python FastAPI container wit h API to:
  - retrieve/refresh the data 
  - process the data
  - generate "small linear regression ML algorithm" model to correlate the tourist attendance at their museums with the population of the respective cities. 
  - store results
- python notebook server container to run the notebook which will call the FastAPI container  

Questions:
- what kind of database to store the raw data and correlation data?
- which source to use to find cities population?
- which Wikipedia API? This one https://www.mediawiki.org/wiki/Wikimedia_REST_API ?

- "small, common and harmonized database" to extract features, what kind of processing to do?
