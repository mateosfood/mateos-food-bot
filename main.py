import json
import os
from flask import Flask, jsonify, request
from google.oauth2.service_account import Credentials
import gspread
import requests

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
  # Verificación inicial del webhook
  if request.method == "GET":
    return "Servidor Webhook activo", 200

  # Cuando llega un mensaje de un cliente por POST
  if request.method == "POST":
    data = request.json
    print("Mensaje recibido:", data)

    try:
      # Extraer datos de la estructura de Evolution API
      incoming_data = data.get("data", {})
      key = incoming_data.get("key", {})

      # Ignorar mensajes enviados por el propio bot para evitar loops
      if key.get("fromMe", False):
        return "OK", 200

      remote_jid = key.get("remoteJid", "")
      # Obtener solo los dígitos del número de teléfono
      telefono = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid

      if not telefono:
        return "No phone found", 200

      # Consultar inventario y armar el menú
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

      # Credenciales y URL de Evolution API desde las variables de entorno de Render
      evo_url = os.environ.get("EVOLUTION_API_URL")
      evo_instance = os.environ.get("EVOLUTION_INSTANCE", "Mateos Food")
      evo_apikey = os.environ.get("EVOLUTION_API_KEY")

      if evo_url and evo_apikey:
        send_url = f"{evo_url}/message/sendText/{evo_instance}"
        headers = {"apikey": evo_apikey, "Content-Type": "application/json"}
        payload = {"number": telefono, "text": mensaje_respuesta}

        res = requests.post(send_url, json=payload, headers=headers)
        print("Respuesta de envío Evolution:", res.status_code, res.text)

    except Exception as e:
      print("Error al procesar el mensaje:", str(e))

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

