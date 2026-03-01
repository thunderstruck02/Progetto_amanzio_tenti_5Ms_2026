from flask import Flask, render_template
import requests
import json
app = Flask(__name__)

@app.route('/')
def home():
    base_url = "https://www.dnd5eapi.co"
    url = base_url + "/api/2014/monsters/aboleth"

    raw_response = requests.get(url)
    json_response = raw_response.json()

    print(json_response)
    image_path = json_response["image"]
    image_url = base_url + image_path   # URL completo

    print(image_url)
    return render_template("main.html", image_url=image_url)


@app.route('/new_5e')
def new_5e():
    return render_template("new_5e.html")

@app.route('/mostri')
def mostri():
    return render_template("mostri.html")

@app.route('/pagina_mostro')
def pagina_mostro():
    return render_template("pagina_mostro.html")

@app.route('/oggetti')
def oggetti():
    return render_template("oggetti.html")



@app.route('/incantesimi')
def incantesimi():
    return render_template("incantesimi.html")

if __name__ == "__main__":
    app.run(debug=True)