import json
import os
from flask import Flask, jsonify, request
from google.oauth2.service_account import Credentials
import gspread
import requests

app = Flask(__name__)


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
  return sheet


@app.route("/", methods=["GET"])
def home():
  return "¡Bot de Mateo's Food en línea y conectado!"


@app.route("/probar-inventario", methods=["GET"])
def probar_inventario():
  try:
    sheet = conectar_inventario()
    return {"estado": "éxito", "datos": sheet.get_all_records()}, 200
  except Exception as e:
    return {"estado": "error", "detalles": str(e)}, 500


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
  if request.method == "GET":
    return "Servidor Webhook activo", 200

  if request.method == "POST":
    data = request.json
    try:
      incoming_data = data.get("data", {})
      key = incoming_data.get("key", {})

      if key.get("fromMe", False):
        return "OK", 200

      remote_jid = key.get("remoteJid", "")
      telefono = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid

      if not telefono:
        return "No phone found", 200

      # Extraer el texto que mandó el cliente (compatible con varios formatos de Evolution)
      message_content = incoming_data.get("message", {})
      texto_usuario = ""
      if isinstance(message_content, dict):
        texto_usuario = (
            message_content.get("conversation")
            or message_content.get("extendedTextMessage", {}).get("text")
            or ""
        ).lower()

      sheet = conectar_inventario()
      productos = sheet.get_all_records()

      mensaje_respuesta = ""
      pedido_encontrado = False

      # Buscar si el usuario escribió el nombre de algún producto disponible
      for idx, p in enumerate(productos, start=2):  # La fila 2 en Google Sheets
        nombre_prod = str(p.get("producto", "")).lower()
        if nombre_prod and nombre_prod in texto_usuario:
          stock_actual = int(p.get("stock", 0))
          if stock_actual > 0 and p.get("estado") == "disponible":
            # Descontar 1 en el stock
            nuevo_stock = stock_actual - 1
            sheet.update_cell(idx, 4, nuevo_stock)  # Asumiendo que la columna 4 es Stock

            mensaje_respuesta = (
                f"✅ ¡Pedido confirmado!\n\n"
                f"Has pedido: *{p.get('producto')}* (-$ {p.get('precio')})\n"
                f"¡Gracias por tu compra en Mateo's Food! En breve te lo preparamos."
            )
            pedido_encontrado = True
            break
          else:
            mensaje_respuesta = (
                f"Lo sentimos, *{p.get('producto')}* por el momento"
                " no tiene stock disponible."
            )
            pedido_encontrado = True
            break

      # Si no escribió ningún producto válido, le mostramos el menú
      if not pedido_encontrado:
        mensaje_respuesta = "🍔 *Menú de Mateo's Food* 🍔\n\n"
        for p in productos:
          if p.get("estado") == "disponible":
            mensaje_respuesta += (
                f"• *{p.get('producto')}* - ${p.get('precio')} (Stock:"
                f" {p.get('stock')})\n"
            )
        mensaje_respuesta += (
            "\n¿Qué te gustaría ordenar hoy? Escribe el nombre del platillo tal cual aparece en la lista."
        )

      # Enviar respuesta por Evolution API
      evo_url = os.environ.get("EVOLUTION_API_URL")
      evo_instance = os.environ.get("EVOLUTION_INSTANCE", "Mateos Food")
      evo_apikey = os.environ.get("EVOLUTION_API_KEY")

      if evo_url and evo_apikey:
        send_url = f"{evo_url}/message/sendText/{evo_instance}"
        headers = {"apikey": evo_apikey, "Content-Type": "application/json"}
        payload = {"number": telefono, "text": mensaje_respuesta}
        requests.post(send_url, json=payload, headers=headers)

    except Exception as e:
      print("Error al procesar:", str(e))

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
