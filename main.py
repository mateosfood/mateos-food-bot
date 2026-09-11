from datetime import datetime
import json
import os
import re
import time
from flask import Flask, jsonify, request
from google import genai
from google.genai import types
from google.auth import default
from googleapiclient.discovery import build
import requests

app = Flask(__name__)

# Configuración de credenciales de Google para Sheets y Drive
creds, _ = default()
sheets_service = build("sheets", "v4", credentials=creds)
drive_service = build("drive", "v3", credentials=creds)


def obtener_spreadsheet_id():
  response = (
      drive_service.files()
      .list(
          q=(
              "name='COMANDAS_MATEOS_FOOD' and"
              " mimeType='application/vnd.google-apps.spreadsheet'"
          ),
          spaces="drive",
      )
      .execute()
  )
  files = response.get("files", [])
  if not files:
    response = (
        drive_service.files()
        .list(
            q=(
                "name='Comandas_Mateos_Food' and"
                " mimeType='application/vnd.google-apps.spreadsheet'"
            ),
            spaces="drive",
        )
        .execute()
    )
    files = response.get("files", [])
  if not files:
    raise Exception("❌ No se encontró la hoja en Google Drive.")
  return files[0]["id"]


def registrar_comanda_en_sheets(comanda_data):
  try:
    spreadsheet_id = obtener_spreadsheet_id()
    items_txt = ", ".join([
        f"{item['cantidad']}x {item['producto']} ({item['detalles']})"
        for item in comanda_data.get("items", [])
    ])
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tipo_e = str(comanda_data.get("tipo_entrega")).upper()
    if "DOMICILIO" in tipo_e and comanda_data.get("direccion"):
      tipo_e += f" ({comanda_data.get('direccion')})"

    nueva_fila = [
        fecha_hora,
        comanda_data.get("cliente", "N/A"),
        tipo_e,
        items_txt,
        comanda_data.get("metodo_pago", "N/A"),
        comanda_data.get("total", 0),
    ]

    body = {"values": [nueva_fila]}
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Hoja 1!A:F",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()
    print("📊 ¡Comanda guardada exitosamente en Google Sheets!")
  except Exception as e:
    print(f"⚠️ Error al guardar en Sheets: {e}")


# Configuración segura de Gemini API usando Variable de Entorno
MI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=MI_API_KEY)

prompt_sistema = """
Eres el asistente virtual amable, rápido y eficiente de "Mateo's Food", un negocio de comida con servicio a domicilio y para pasar a recoger ubicado en el pueblo.

TU OBJETIVO:
Atender al cliente por WhatsApp, tomar su pedido exacto, resolver dudas del menú, verificar la zona de entrega, calcular el total y obtener los datos de pago.

MENÚ Y PRECIOS:
- Hamburguesa Normal: $70 (Incluye papas fritas)
- Hamburguesa de Arrachera: $85 (Incluye papas fritas)
- Pirata: $85
- Orden de Tacos de Maíz (5 tacos): $85
- Orden de Tacos de Harina (5 tacos): $90
- Taco individual de Maíz: $23
- Taco individual de Harina: $28
- Orden de Papas Fritas: $45
- Burrito de Frijol con Queso/Pizza: $30 c/u
- Orden de Quesadillas de Harina (5 quesadillas): $85

REGLAS DE ZONAS, ENVÍO Y TIEMPOS (¡MUY IMPORTANTE!):
1. **Zonas de Entrega permitidas:** Solo entregamos en **Carbonera Sur** y **Carbonera Norte** (en Carbonera Norte el límite de entrega es exclusivamente hasta la tienda "Feily"). Si el cliente pide de más lejos o de otro lugar, acláralo amablemente indicando que por el momento no abarcamos esa zona.
2. **Costo de Envíos:** El envío es **GRATIS** ($0) en todas las zonas de entrega.
3. **Tiempos de entrega:** El tiempo estándar estimado para cualquier domicilio es de **30 minutos**.

REGLAS DE ATENCIÓN:
1. Sé siempre amable, claro y breve (respuestas estilo WhatsApp).
2. Pregunta si las hamburguesas o tacos llevan alguna modificación (ej. sin verdura, sin aderezos).
3. Pregunta si el pedido es A DOMICILIO o PARA PASAR A RECOGER.
4. Si es A DOMICILIO, pide la dirección exacta, asegúrate de que esté dentro de Carbonera Sur o Carbonera Norte (recordando el límite de la tienda Feily en el norte) y recuérdale que el tiempo estimado es de 30 minutos sin costo de envío.
5. Pregunta el **método de pago (efectivo, transferencia o tarjeta)**. Si es en efectivo, pregunta con cuánto va a pagar para calcular el cambio. Si es con tarjeta (a domicilio), recuérdale que llevamos la terminal o coordina el cobro.
6. AL CONFIRMAR EL PEDIDO: Muestra el resumen al cliente (incluyendo el tiempo estimado de 30 min y envío gratis) y, al final de tu mensaje, incluye la comanda en formato JSON encerrada entre ```json ... ``` con la siguiente estructura:
{
"tipo_entrega": "domicilio / recoger",
"cliente": "Nombre",
"direccion": "Dirección completa (Zona: Carbonera Norte/Sur)",
"items": [{"producto": "Nombre", "cantidad": 1, "detalles": "Sin cebolla", "precio_unitario": 85}],
"metodo_pago": "efectivo / transferencia / tarjeta",
"paga_con": 200,
"cambio": 115,
"total": 85
}
"""

sesiones_clientes = {}


def obtener_o_crear_chat(cliente_id):
  if cliente_id not in sesiones_clientes:
    print(f"✨ Creando nueva sesión de chat para el cliente: {cliente_id}")
    sesiones_clientes[cliente_id] = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=prompt_sistema, temperature=0.3
        ),
    )
  return sesiones_clientes[cliente_id]


@app.route("/", methods=["GET"])
def home():
  return "¡Bot con personalidad de Mateo's Food en línea!"


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

      push_name = incoming_data.get("pushName", "Cliente")

      message_content = incoming_data.get("message", {})
      texto_usuario = ""
      if isinstance(message_content, dict):
        texto_usuario = (
            message_content.get("conversation")
            or message_content.get("extendedTextMessage", {}).get("text")
            or ""
        ).strip()

      if not texto_usuario:
        return "EVENT_RECEIVED", 200

      chat_activo = obtener_o_crear_chat(telefono)
      respuesta = chat_activo.send_message(texto_usuario)
      texto_respuesta = respuesta.text

      match = re.search(r"```json\s*(\{.*?\})\s*```", texto_respuesta, re.DOTALL)
      if match:
        json_str = match.group(1)
        try:
          comanda = json.loads(json_str)
          if "cliente" not in comanda or comanda["cliente"] == "Nombre":
            comanda["cliente"] = push_name
          print("--------------------------------------------------")
          print(f"🚀 PROCESANDO COMANDA DE {telefono}...")
          registrar_comanda_en_sheets(comanda)
          print("--------------------------------------------------\n")
        except json.JSONDecodeError as je:
          print("Error al decodificar JSON de comanda:", je)

      evo_url = os.environ.get("EVOLUTION_API_URL")
      evo_instance = os.environ.get("EVOLUTION_INSTANCE", "Mateos Food")
      evo_apikey = os.environ.get("EVOLUTION_API_KEY")

      if evo_url and evo_apikey:
        send_url = f"{evo_url}/message/sendText/{evo_instance}"
        headers = {"apikey": evo_apikey, "Content-Type": "application/json"}
        payload = {"number": telefono, "text": texto_respuesta}
        requests.post(send_url, json=payload, headers=headers)

    except Exception as e:
      print("Error crítico en webhook:", str(e))

    return "EVENT_RECEIVED", 200


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
