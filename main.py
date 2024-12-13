from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.websockets import WebSocketState
import requests
from datetime import datetime
import traceback
import json
import subprocess
import asyncio
import os
import logging
import chardet



def format_timestamp(ts):
    if ts:
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
            return dt.strftime("%d.%m.%Y %H:%M")
        except:
            return ts
    return "Unbekannt"

def get_domain_from_url(url):
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except:
        return url

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.mount("/static", StaticFiles(directory="static"), name="static")

def get_article_metadata(article_title):
    baseurl_wikipedia = "https://de.wikipedia.org/w/api.php"

    # Hauptabfrage
    params_wikipedia = {
            "action": "query",
            "format": "json",
            "titles": article_title,
            "prop": "revisions|categories|info|links|extlinks|images|templates|langlinks|contributors|pageviews|extracts|coordinates|pageprops",
            "rvprop": "timestamp|user|comment|size|ids",
            "rvlimit": "max",
            "inprop": "url|displaytitle|watchers|visitors|modified",
            "explaintext": 1,
            "exintro": 1,
            "llprop": "url|langname|autonym",
            "lllimit": "max",

        }

    try:
        response = requests.get(baseurl_wikipedia, params=params_wikipedia)
        data = response.json()
        pages = data.get("query", {}).get("pages", {})

        if not pages:
            return None

        page = next(iter(pages.values()))

        print(page)

        if "missing" in page:
            return None

        # Erstellungs- und Änderungsdaten abrufen
        params_history = {
            "action": "query",
            "format": "json",
            "titles": article_title,
            "prop": "revisions",
            "rvprop": "timestamp|user|comment",
            "rvlimit": 1,
            "rvdir": "newer"  # Älteste Revision (Erstellung)
        }

        history_response = requests.get(baseurl_wikipedia, params=params_history)
        history_data = history_response.json()
        creation_info = None
        if "query" in history_data:
            history_pages = history_data["query"]["pages"]
            history_page = next(iter(history_pages.values()))
            if "revisions" in history_page:
                creation_info = history_page["revisions"][0]


        metadata = {
            "basic_info": {
                            "title": page.get("title"),
                            "url": page.get("fullurl"),
                            "length": page.get("length"),
                            "page_id": page.get("pageid"),
                            "created": format_timestamp(creation_info.get("timestamp") if creation_info else None),
                            "created_by": creation_info.get("user") if creation_info else "Unbekannt",
                            "last_modified": format_timestamp(page.get("touched")),
                            "watchers": page.get("watchers"),
                            "page_views": page.get("pageviews", {})
                        },
            "content": {
                "extract": page.get("extract"),
                "categories": [cat["title"] for cat in page.get("categories", [])],
                "templates": [template["title"] for template in page.get("templates", [])]
            },
            "references": {
                "external_links": [link.get("*") for link in page.get("extlinks", [])],
                "internal_links": [link["title"] for link in page.get("links", [])]
            },
            "history": {
                "revisions": [{
                    "user": rev.get("user", "Unbekannt"),
                    "timestamp": rev.get("timestamp", ""),
                    "comment": rev.get("comment", "Keine Zusammenfassung"),
                    "size": rev.get("size", 0)
                } for rev in page.get("revisions", [])]
            },
            "languages": {
                "available_versions": [{
                    "lang": lang.get("lang", ""),
                    "title": lang.get("*", ""),
                    "url": lang.get("url", ""),
                    "language_name": lang.get("langname", ""),
                    "autonym": lang.get("autonym", "")  # Name der Sprache in der jeweiligen Sprache
                } for lang in page.get("langlinks", [])]
            }
        }

        external_links = []
        if "extlinks" in page:
            for link in page.get("extlinks", []):
                url = link.get("*", "")
                domain = get_domain_from_url(url).lower()

                # Link-Typ bestimmen
                link_type = "other"
                if any(news in domain for news in ["news.", "focus.", "taz.", "zeit.", "spiegel.", "faz.", "fau-archiv.", "sueddeutsche.", "tagesschau.", "welt.", "stern."]):
                    link_type = "news"
                elif any(academic in domain for academic in [".edu", ".ac.", "scholar.", "research.", "uni-", "university", "academia"]):
                    link_type = "academic"
                elif any(social in domain for social in ["twitter.", "facebook.", "linkedin.", "youtube.", "instagram.", "tiktok."]):
                    link_type = "social"
                elif any(gov in domain for gov in [".gov", ".gv.", "bundes", "parlament", "europa.eu"]):
                    link_type = "government"

                external_links.append({
                    "url": url,
                    "domain": domain,
                    "type": link_type,
                    "protocol": url.split("://")[0] if "://" in url else "unknown",
                    "is_secure": url.startswith("https"),
                })

        # Gruppiere Links nach Domains und Typen
        domain_stats = {}
        type_stats = {
            "news": 0,
            "academic": 0,
            "social": 0,
            "government": 0,
            "other": 0
        }
        protocol_stats = {
            "http": 0,
            "https": 0,
            "other": 0
        }

        print(f"external_links {external_links}")
        for link in external_links:
            # Domain-Statistiken
            if link["domain"] in domain_stats:
                domain_stats[link["domain"]]["count"] += 1
            else:
                domain_stats[link["domain"]] = {
                    "count": 1,
                    "type": link["type"],
                    "example_url": link["url"]
                }

            # Typ-Statistiken
            type_stats[link["type"]] += 1

            # Protokoll-Statistiken
            if link["protocol"] in ["http", "https"]:
                protocol_stats[link["protocol"]] += 1
            else:
                protocol_stats["other"] += 1

            # Top-Domains ermitteln
            top_domains = dict(sorted(
                domain_stats.items(),
                key=lambda x: x[1]["count"],
                reverse=True
            )[:10])

            try:
                metadata["references"] = {
                    "external_links": external_links,
                    "internal_links": [link["title"] for link in page.get("links", [])],
                    "summary": {
                        "total_count": len(external_links),
                        "secure_links": len([link for link in external_links if link["is_secure"]]),
                        "types": type_stats,
                        "protocols": protocol_stats,
                        "top_domains": top_domains,
                        "domain_count": len(domain_stats)
                    }
                }
            except Exception as e:
                print(f"Error creating references summary: {e}")
                metadata["references"] = {
                    "external_links": [],
                    "internal_links": [],
                    "summary": {
                        "total_count": 0,
                        "secure_links": 0,
                        "types": {"news": 0, "academic": 0, "social": 0, "government": 0, "other": 0},
                        "protocols": {"http": 0, "https": 0, "other": 0},
                        "top_domains": {},
                        "domain_count": 0
                    }
                }
        print(metadata)
        metadata["languages"]["available_versions"].sort(key=lambda x: x["language_name"])
        # Füge die Anzahl der verfügbaren Sprachen hinzu
        metadata["languages"]["count"] = len(metadata["languages"]["available_versions"])

        if "images" in page:
                    image_titles = [img["title"] for img in page["images"]]
                    params_images = {
                        "action": "query",
                        "format": "json",
                        "titles": "|".join(image_titles),
                        "prop": "imageinfo",
                        "iiprop": "url|size|mime|extmetadata",
                        "iiurlwidth": 800  # Maximale Breite der Bilder
                    }

                    images_response = requests.get(baseurl_wikipedia, params=params_images)
                    images_data = images_response.json()

                    if "query" in images_data and "pages" in images_data["query"]:
                        images = []
                        for img_page in images_data["query"]["pages"].values():
                            if "imageinfo" in img_page:
                                for info in img_page["imageinfo"]:
                                    # Bildtitel aus dem Dateinamen extrahieren und formatieren
                                    raw_title = img_page.get("title", "")
                                    # Entferne "File:" oder "Datei:" vom Anfang und ".jpg", ".png" etc. vom Ende
                                    clean_title = raw_title.replace("File:", "").replace("Datei:", "")
                                    clean_title = ' '.join(clean_title.split('_'))  # Ersetze Unterstriche durch Leerzeichen

                                    # Hole zusätzliche Metadaten falls verfügbar
                                    ext_metadata = info.get("extmetadata", {})
                                    description = ext_metadata.get("ImageDescription", {}).get("value", "")

                                    images.append({
                                        "title": clean_title,
                                        "raw_title": raw_title,
                                        "url": info.get("url", ""),
                                        "thumb_url": info.get("thumburl", ""),
                                        "mime": info.get("mime", ""),
                                        "size": info.get("size", 0),
                                        "width": info.get("width", 0),
                                        "height": info.get("height", 0),
                                        "description": description
                                    })
                        metadata["images"] = images

        # Zusätzliche Abfrage für Contributors
        params_contributors = {
            "action": "query",
            "prop": "contributors",
            "titles": article_title,
            "pclimit": 500,
            "format": "json"
        }

        params_stats = {
                    "action": "query",
                    "prop": "revisions",
                    "titles": article_title,
                    "rvprop": "timestamp|user|size",
                    "rvlimit": "max",
                    "format": "json"
                }

        stats_response = requests.get(baseurl_wikipedia, params=params_stats)
        stats_data = stats_response.json()
        if "query" in stats_data:
            stats_pages = stats_data["query"]["pages"]
            stats_page = next(iter(stats_pages.values()))
            if "revisions" in stats_page:
                revisions = stats_page["revisions"]
                metadata["statistics"] = {
                    "total_revisions": len(revisions),
                    "first_edit": format_timestamp(revisions[-1].get("timestamp")),
                    "last_edit": format_timestamp(revisions[0].get("timestamp")),
                    "unique_editors": len(set(rev.get("user", "") for rev in revisions))
                }

        contributors_response = requests.get(baseurl_wikipedia, params=params_contributors)
        contributors_data = contributors_response.json()
        if "query" in contributors_data:
            contributors_pages = contributors_data["query"]["pages"]
            page_contributors = next(iter(contributors_pages.values()))
            metadata["contributors"] = [
                {
                    "name": contributor.get("name"),
                    "userid": contributor.get("userid")
                }
                for contributor in page_contributors.get("contributors", [])
            ]

        return metadata

    except Exception as e:
        print(f"Fehler beim Abrufen der Metadaten: {str(e)}")
        return None

def search_wikipedia_articles(search_term):
    baseurl_wikipedia = "https://de.wikipedia.org/w/api.php"

    # Erste Suche für Artikel
    search_params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": search_term,
        "srlimit": "max",
        "srprop": "snippet",
        "prop": "info|extracts|pageimages",
        "inprop": "url",
        "pithumbsize": 200,
        "explaintext": 1,
        "exintro": 1
    }

    try:
        print(f"Searching for: {search_term}")
        response = requests.get(baseurl_wikipedia, params=search_params)
        data = response.json()
        print(f"Initial search response: {json.dumps(data, indent=2)}")  # Debug output

        suggestions = []

        # Verarbeite Suchergebnisse
        if 'query' in data and 'search' in data['query']:
            for result in data['query']['search']:
                suggestion = {
                    "title": result.get('title', ''),
                    "pageid": result.get('pageid', ''),
                    "snippet": result.get('snippet', '').replace('<span class="searchmatch">', '<mark>').replace('</span>', '</mark>'),
                    "url": f"https://de.wikipedia.org/wiki/{result.get('title', '').replace(' ', '_')}"
                }
                suggestions.append(suggestion)
                print(f"Added suggestion: {suggestion['title']}")  # Debug output

        # Wenn keine Ergebnisse, versuche alternative Suche
        if not suggestions:
            alt_params = {
                "action": "opensearch",
                "search": search_term,
                "limit": 10,
                "namespace": 0,
                "format": "json"
            }

            alt_response = requests.get(baseurl_wikipedia, params=alt_params)
            alt_data = alt_response.json()
            print(f"Alternative search response: {json.dumps(alt_data, indent=2)}")  # Debug output

            if len(alt_data) >= 4:
                for i in range(len(alt_data[1])):
                    suggestions.append({
                        "title": alt_data[1][i],
                        "description": alt_data[2][i],
                        "url": alt_data[3][i]
                    })

        # "Meinten Sie" Vorschläge
        didyoumean_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srnamespace": "0",
            "srsearch": search_term,
            "srinfo": "suggestion"
        }

        dym_response = requests.get(baseurl_wikipedia, params=didyoumean_params)
        dym_data = dym_response.json()
        print(f"Did you mean response: {json.dumps(dym_data, indent=2)}")  # Debug output

        if 'query' in dym_data and 'searchinfo' in dym_data['query']:
            if 'suggestion' in dym_data['query']['searchinfo']:
                suggestions.append({
                    "title": dym_data['query']['searchinfo']['suggestion'],
                    "is_suggestion": True
                })

        print(f"Final suggestions count: {len(suggestions)}")
        print(f"Final suggestions: {json.dumps(suggestions, indent=2)}")  # Debug output
        return suggestions

    except Exception as e:
        print(f"Error in search: {str(e)}")
        traceback.print


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    print(os.getcwd())
    return templates.TemplateResponse("wiki.html", {"request": request})

@app.post("/get_metadata", response_class=HTMLResponse)
async def get_metadata(request: Request, article_title: str = Form(...)):
    print("Starting get_metadata for article:", article_title)
    metadata = get_article_metadata(article_title)

    if not metadata:
        suggestions = search_wikipedia_articles(article_title)
        return templates.TemplateResponse("wiki.html", {
            "request": request,
            "error": f"Der Artikel '{article_title}' wurde nicht gefunden.",
            "suggestions": suggestions,
            "article_title": article_title
        })

    # Stelle sicher, dass die komplette Struktur existiert
    if 'references' not in metadata:
        metadata['references'] = {}
    if 'summary' not in metadata['references']:
        metadata['references']['summary'] = {}

    # Stelle sicher, dass alle erforderlichen Unterstrukturen existieren
    default_summary = {
        'types': {
            'news': 0,
            'academic': 0,
            'social': 0,
            'government': 0,
            'other': 0
        },
        'total_count': 0,
        'secure_links': 0,
        'protocols': {
            'http': 0,
            'https': 0,
            'other': 0
        },
        'top_domains': {},  # Leeres dict für top_domains
        'domain_count': 0
    }

    # Update die summary-Struktur mit den Standardwerten
    metadata['references']['summary'] = {
        **default_summary,
        **metadata['references'].get('summary', {})
    }

    return templates.TemplateResponse("wiki.html", {
        "request": request,
        "metadata": metadata,
        "article_title": article_title
    })

@app.get("/aufgabe6-4", response_class=HTMLResponse)
async def aufgabe6_4(request: Request):
    return templates.TemplateResponse("aufgabe6-4.html", {"request": request})

@app.websocket("/ws/llama")
async def llama_stream(websocket: WebSocket):
    await websocket.accept()
    logging.info("WebSocket accepted")

    process = None
    try:
        logging.info("Starting llama-cli process in interactive mode")

        # Start llama-cli im interaktiven Modus
        process = await asyncio.create_subprocess_exec(
            "./llama.cpp/build/bin/llama-cli",
            "-m", "./llama.cpp/models/Llama-3.2-1B-Instruct-Q5_K_M.gguf",
            "--interactive",
            "--conversation",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE
        )

        logging.info("llama-cli process started")

        # Lese den Output des Prozesses Zeichenweise
        async def read_output():
            while True:
                byte = await process.stdout.read(1)
                if not byte:
                    break
                try:
                    if byte.decode('utf-8'):
                        char = byte.decode('utf-8')
                    elif byte.decode('latin'):
                        char = byte.decode('latin')
                    elif byte.decode('tis-620'):
                        char = byte.decode('tis-620')
                    elif byte.decode('iso-8859-5'):
                        char = byte.decode('iso-8859-5')
                    else:
                        char = byte.decode('utf-16')

                    logging.debug(f"Process output: {char}")
                    if websocket.client_state == WebSocketState.CONNECTED:
                        await websocket.send_text(char)
                except UnicodeDecodeError:
                    logging.error("Failed to decode byte, skipping it")
                    continue

        asyncio.create_task(read_output())

        while True:
            user_message = await websocket.receive_text()
            logging.debug(f"Received message: {user_message}")
            if user_message:
                process.stdin.write(user_message.encode() + b'\n')
                await process.stdin.drain()

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(f"Unerwarteter Fehler: {str(e)}")

    finally:
        if process:
            process.terminate()
            logging.info("Terminating llama-cli process")

        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close()
            logging.info("WebSocket closed")
