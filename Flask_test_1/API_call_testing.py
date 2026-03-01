import requests
import json
from time import strftime


"""ESEMPI DI RICHIESTE"""


import matplotlib
import matplotlib.pyplot as plt
from datetime import datetime
import sqlite3

def api_call(given_url):
    url = given_url
    response = requests.get(url)
    print(response.json())
    formatted = json.dumps(response.json(), indent=4)
    return formatted

API_response = api_call("https://www.dnd5eapi.co/api/2014/")
print(API_response)