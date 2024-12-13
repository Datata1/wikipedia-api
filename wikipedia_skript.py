import requests

def get_article_metadata(article_title):
    url = "https://de.wikipedia.org/w/api.php"

    # In zwei Abfragen unterteil, da die letzte und die erste Revision nicht in einer Abfrage abgefragt werden können
    creation_params = {
        "action": "query", 
        "format": "json",
        "titles": article_title, 
        "prop": "revisions", 
        "rvprop": "timestamp",
        "rvlimit": 500,
        "rvdir": "newer",  
    }
    other_params = {
        "action": "query", 
        "format": "json", 
        "titles": article_title, 
        "prop": "revisions|categories", #
        "rvprop": "timestamp",
        "rvlimit": 500,
        "rvdir": "older",  
    }

    # Anfrage an die Wikipedia API
    creation_response = requests.get(url, params=creation_params)
    others_response = requests.get(url, params=other_params)

    # Daten aus der Antwort extrahieren
    creation_data = creation_response.json()
    others_data = others_response.json()

    creation_pages = creation_data.get("query").get("pages")
    creation_first_page = next(iter(creation_pages.values()))
    
    others_pages = others_data.get("query").get("pages")
    others_first_page = next(iter(others_pages.values()))

    # Erste und letzte Überarbeitung
    creation_date = creation_first_page.get('revisions')[0].get('timestamp')
    last_revision = others_first_page.get('revisions')[0].get('timestamp')

    # Anzahl der Überarbeitungen
    new_revisions = others_first_page.get('revisions')
    old_revisions = creation_first_page.get('revisions')

    # List-Comprehension, um die Zeitstempel der Überarbeitungen zu extrahieren
    new_revisions = [item.get('timestamp') for item in new_revisions]
    old_revisions = [item.get('timestamp') for item in old_revisions]

    # Anzahl der Überarbeitungen berechnen
    count_revisions = 0
    # Überprüfen, ob die Zeitstempel der neuen Überarbeitungen in den alten Überarbeitungen enthalten sind
    for item in new_revisions:
        if item not in old_revisions:
            count_revisions += 1

    count_revisions += len(old_revisions)

    categories = others_first_page.get('categories')

    print("Erstellungsdatum:", creation_date)
    print("Letzte Überarbeitung:", last_revision)

    # Wenn die Anzahl der Überarbeitungen 500 ist, wird ein "+" angehängt
    if count_revisions == 1000:
        print(f"Anzahl der Überarbeitungen: {count_revisions}+")
    else:
        print(f"Anzahl der Überarbeitungen: {count_revisions}")
    
    print(f"\nKategorien:")
    for item in categories:
        category = item.get('title')
        category = category.split(":")[1]
        print(category)


if __name__ == "__main__":
    article_title = input("Bitte geben Sie den Titel des Wikipedia-Artikels ein: ")
    get_article_metadata(article_title)
