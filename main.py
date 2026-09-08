import json
import os
from flask import Flask, jsonify, request
from google.oauth2.service_account import Credentials
import gspread

app = Flask(__name__)


# Configurar conexión con Google Sheets usando la variable de entorno
def conectar_inventario():
  scope = [
      "https://www.googleapis.com/auth/spreadsheets",
      "https://www.googleapis.com/auth/drive",
  ]
  creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
  creds_dict = json.loads(creds_json)

  creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
  client = gspread.authorize(creds)

  sheet = client.open("Inventario Mateos Food").worksheet("Productos")
  return sheet.get_all_records()


@app.route("/", methods=["GET"])
def home():
  return "¡Bot de Mateo's Food en línea y conectado!"


# Ruta de diagnóstico que ya probamos
@app.route("/probar-inventario", methods=["GET"])
def probar_inventario():
  try:
    productos = conectar_inventario()
    return {"estado": "éxito", "datos": productos}, 200
  except Exception as e:
    return {"estado": "error", "detalles": str(e)}, 500


# Webhook para recibir y responder mensajes de WhatsApp
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
  # Verificación inicial del webhook (Meta/WhatsApp pide esto)
  if request.method == "GET":
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
      if mode == "subscribe" and token == "mateos_token":
        return challenge, 200
      else:
        return "Token inválido", 403
    return "Servidor Webhook activo", 200

  # Cuando llega un mensaje de un cliente por POST
  if request.method == "POST":
    data = request.json
    print("Mensaje recibido:", data)

    try:
      productos = conectar_inventario()
      mensaje_respuesta = "🍔 *Menú de Mateo's Food* 🍔\n\n"
      for p in productos:
        if p.get("estado") == "disponible":
          mensaje_respuesta += (
              f"• *{p.get('producto')}* - ${p.get('precio')} (Stock:"
              f" {p.get('stock')})\n"
          )
      mensaje_respuesta += (
          "\n¿Qué te gustaría ordenar hoy? Responde con tu pedido."
      )
      print("Respuesta generada para enviar:", mensaje_respuesta)
    except Exception as e:
      print("Error al procesar el inventario:", str(e))

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
