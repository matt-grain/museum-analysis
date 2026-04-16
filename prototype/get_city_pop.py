import pandas as pd
import requests


def get_qid_by_name(city_name):
    url = "https://www.wikidata.org/w/api.php"

    # Wikimedia requires a custom User-Agent.
    # Best practice is: "ProjectName/Version (Contact info/URL)"
    headers = {
        'User-Agent': 'CityDataFetcher/1.0 (https://example.org; contact@example.com)'
    }

    params = {
        "action": "wbsearchentities",
        "language": "en",
        "format": "json",
        "search": city_name
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()  # This will catch other HTTP errors
        data = response.json()

        if data.get('search'):
            # Returning the QID of the top result
            return data['search'][0]['id']
        return None

    except requests.exceptions.HTTPError as e:
        return f"HTTP Error: {e}"
    except Exception as e:
        return f"An error occurred: {e}"


def get_population_history(city_qids):
    endpoint_url = "https://query.wikidata.org/sparql"
    qids_formatted = " ".join([f"wd:{qid}" for qid in city_qids])

    # Query uses BIND(YEAR(?date) AS ?year) to make filtering/grouping easier
    query = f"""
    SELECT ?cityLabel ?population ?year
    WHERE {{
      VALUES ?city {{ {qids_formatted} }}
      ?city p:P1082 ?statement .
      ?statement ps:P1082 ?population .
      ?statement pq:P585 ?date .
      
      # Filter for years 2000 and newer
      BIND(YEAR(?date) AS ?year)
      FILTER(?year >= 2000)
      
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY ?cityLabel ?year
    """

    headers = {
        'User-Agent': 'CityHistoryBot/1.0 (contact@example.org)',
        'Accept': 'application/sparql-results+json'
    }

    try:
        response = requests.get(endpoint_url, params={'query': query, 'format': 'json'}, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Dictionary to store { (City, Year): Population } to handle duplicates
        history = {}

        for result in data['results']['bindings']:
            city = result['cityLabel']['value']
            year = result['year']['value']
            pop = int(result['population']['value'])

            # Keep the highest population value if multiple exist for the same year
            key = (city, year)
            if key not in history or pop > history[key]:
                history[key] = pop

        return history

    except Exception as e:
        print(f"Error fetching data: {e}")
        return {}

cities = ["Paris", "London", "Tokyo"]
qids = []
for city in cities:
    qids.append(get_qid_by_name(city))


population_data = get_population_history(qids)

# Print the results in a formatted table
print(f"{'City':<15} | {'Year':<6} | {'Population'}")
print("-" * 35)

# Sort by city name and then by year for the output
for (city, year) in sorted(population_data.keys()):
    print(f"{city:<15} | {year:<6} | {population_data[(city, year)]:>10,}")

# 2. Convert dictionary to a list of dictionaries for pandas
formatted_list = [
    {'City': city, 'Year': year, 'Population': pop}
    for (city, year), pop in population_data.items()
]

# 3. Create DataFrame and save
df = pd.DataFrame(formatted_list)

# Sort the data for a cleaner file
df = df.sort_values(by=['City', 'Year'])

df.to_csv("city_population_history.csv", index=False, encoding='utf-8')
print("CSV saved successfully.")
