import pandas as pd
import requests


def get_high_traffic_museums(threshold=2000000):
    endpoint_url = "https://query.wikidata.org/sparql"

    # SPARQL Query logic:
    # 1. ?item is an instance of 'museum' (Q33506) or its subclasses.
    # 2. Extract visitors (P1174) and filter by threshold.
    # 3. Get country (P17) and city/location (P131 or P159).
    query = f"""
    SELECT DISTINCT ?museumLabel ?cityLabel ?countryLabel ?visitors ?year
    WHERE {{
      ?museum wdt:P31/wdt:P279* wd:Q33506 .  # Instance of museum
      
      # Get visitor statement and qualifiers
      ?museum p:P1174 ?vStatement .
      ?vStatement ps:P1174 ?visitors .
      OPTIONAL {{ ?vStatement pq:P585 ?date . }}
      BIND(YEAR(?date) AS ?year)
      
      FILTER(?visitors > {threshold})
      
      # Get Country
      ?museum wdt:P17 ?country .
      
      # Get City (try administrative entity P131 or headquarters P159)
      OPTIONAL {{ ?museum wdt:P131 ?city . }}
      OPTIONAL {{ ?museum wdt:P159 ?city . }}
      
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    ORDER BY DESC(?visitors)
    """

    headers = {
        'User-Agent': 'MuseumDataBot/1.0 (contact@example.org)',
        'Accept': 'application/sparql-results+json'
    }

    try:
        response = requests.get(endpoint_url, params={'query': query, 'format': 'json'}, headers=headers)
        response.raise_for_status()
        data = response.json()

        results = []
        # Use a set to ensure unique museums in the output
        seen_museums = set()

        for result in data['results']['bindings']:
            name = result['museumLabel']['value']
            if name not in seen_museums:
                results.append({
                    "museum": name,
                    "city": result.get('cityLabel', {}).get('value', "Unknown"),
                    "country": result.get('countryLabel', {}).get('value', "Unknown"),
                    "visitors": int(float(result['visitors']['value'])),
                    "year": result.get('year', {}).get('value', "N/A")
                })
                seen_museums.add(name)

        return results

    except Exception as e:
        print(f"Error: {e}")
        return []

# Execute and Print
museum_list = get_high_traffic_museums()

print(f"{'Museum':<40} | {'City':<15} | {'Country':<12} | {'Visitors'}")
print("-" * 85)
for m in museum_list:
    print(f"{m['museum'][:40]:<40} | {m['city']:<15} | {m['country']:<12} | {m['visitors']:,}")

df = pd.DataFrame(museum_list)
csv_filename = "highly_visited_museums.csv"
df.to_csv(csv_filename, index=False)
print(f"File saved as {csv_filename}")
