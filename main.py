import json
import os
from flask import Flask, request
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)


# Configurar conexión con Google Sheets usando la variable de entorno
def conectar_inventario():
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  # Lee la llave JSON que guardamos en Render
  creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
  creds_dict = json.loads(creds_json)

  creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
  client = gspread.authorize(creds)

  # Abre tu hoja y la pestaña (cambia 'Productos' si la nombraste distinto)
  sheet = client.open("Inventario Mateos Food").worksheet("Productos")
  return sheet.get_all_records()


@app.route("/", methods=["GET"])
def home():
  return "¡Bot de Mateo's Food en línea y conectado!"


@app.route("/webhook", methods=["POST"])
def webhook():
  # Aquí es donde recibiremos los mensajes de WhatsApp
  datos_menu = conectar_inventario()
  print("Inventario leído con éxito:", datos_menu)
  return "OK", 200


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
