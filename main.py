from datetime import datetime
import json
import os
import re
import time
from flask import Flask, jsonify, request
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import requests

app = Flask(__name__)

# Configuración de credenciales de Google
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Configuración de Evolution API y Teléfono de Cocina desde Variables de Entorno
EVO_URL = os.environ.get("EVOLUTION_API_URL")
EVO_INSTANCE = os.environ.get("EVOLUTION_INSTANCE", "Mateos Food")
EVO_APIKEY = os.environ.get("EVOLUTION_API_KEY")
NUMERO_COCINA = os.environ.get("NUMERO_COCINA", "") # Ej: 521XXXXXXXXXX


def obtener_servicios_google():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("❌ Falta la variable de entorno GOOGLE_CREDENTIALS_JSON.")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    sheets_s = build("sheets", "v4", credentials=creds)
    drive_s = build("drive", "v3", credentials=creds)
    return sheets_s, drive_s


def obtener_spreadsheet_id():
    _, drive_service = obtener_servicios_google()
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


# --- CAMBIO 2: OBTENER MENÚ DINÁMICO DE GOOGLE SHEETS ---
def obtener_menu_dinamico():
    """Lee el menú desde la pestaña 'MENU' en Google Sheets (Columnas A y B: Producto | Precio)."""
    menu_default = """
- Hamburguesa Normal: $75 (Incluye papas fritas)
- Hamburguesa de Arrachera: $85 (Incluye papas fritas)
- Pirata: $85
- Orden de Tacos de Maíz (5 tacos): $85
- Orden de Tacos de Harina (5 tacos): $90
- Taco individual de Maíz: $23
- Taco individual de Harina: $28
- Orden de Papas Fritas: $45
- Burrito de Frijol con Queso/Pizza: $30 c/u
- Orden de Quesadillas de Harina (5 quesadillas): $85
"""
    try:
        sheets_service, _ = obtener_servicios_google()
        spreadsheet_id = obtener_spreadsheet_id()
        resultado = sheets_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range="MENU!A2:B30"
        ).execute()
        filas = resultado.get("values", [])
        if not filas:
            return menu_default
        
        lineas_menu = []
        for fila in filas:
            if len(fila) >= 2:
                lineas_menu.append(f"- {fila[0]}: ${fila[1]}")
        return "\n".join(lineas_menu)
    except Exception as e:
        print(f"⚠️ No se pudo cargar menú de Sheets, usando default: {e}")
        return menu_default


def construir_prompt_sistema():
    menu_actualizado = obtener_menu_dinamico()
    return f"""
Eres el asistente virtual amable, rápido y eficiente de "Mateo's Food", un negocio de comida con servicio a domicilio y para pasar a recoger ubicado en el pueblo.

TU OBJETIVO:
Atender al cliente por WhatsApp, tomar su pedido exacto, resolver dudas del menú, verificar la zona de entrega, calcular el total y obtener los datos de pago.

MENÚ Y PRECIOS ACTUALIZADOS:
{menu_actualizado}

DATOS PARA TRANSFERENCIA BANCARIA:
- Banco: Banco Azteca
- CLABE Interbancaria: 127824001322868211
- A nombre de: Adrian Mateos
*(Cuando el cliente elija pago por transferencia, proporciónale estos datos amablemente y recuérdale que te mande su comprobante).*

REGLAS DE ZONAS, ENVÍO Y TIEMPOS (¡MUY IMPORTANTE!):
1. **Zonas de Entrega permitidas:** Solo entregamos en **Carbonera Sur** y **Carbonera Norte** (en Carbonera Norte el límite de entrega es exclusivamente hasta la tienda "Feily"). Si el cliente pide de más lejos o de otro lugar, acláralo amablemente indicando que por el momento no abarcamos esa zona.
2. **Costo de Envíos:** El envío es **GRATIS** ($0) en todas las zonas de entrega.
3. **Tiempos de entrega:** El tiempo estándar estimado para cualquier domicilio es de **30 minutos**.

INSTRUCCIONES DE ENTREGA:
- Para entregas a domicilio, NUNCA pidas calle y número exacto. Pregunta directo: "¿Es para Carbonera Norte o Carbonera Sur? ¿Qué referencia cercana tienes?"
- Asegúrate de respetar el límite de la tienda "Feily" si es Carbonera Norte.
- Si el cliente ya mencionó su zona/referencia en mensajes anteriores de esta misma conversación, NO se la vuelvas a pedir; solo confirma: "¿Mismo domicilio en Carbonera [Norte/Sur] ([referencia])?".

REGLAS DE ATENCIÓN:
1. Sé siempre amable, claro y breve (respuestas estilo WhatsApp).
2. Pregunta si las hamburguesas o tacos llevan alguna modificación (ej. sin verdura, sin aderezos).
3. Pregunta si el pedido es A DOMICILIO o PARA PASAR A RECOGER.
4. Si es A DOMICILIO, aplica las INSTRUCCIONES DE ENTREGA de arriba y recuérdale que el tiempo estimado es de 30 minutos sin costo de envío.
5. Pregunta el método de pago (efectivo, transferencia o tarjeta). Si es en efectivo, pregunta con cuánto va a pagar para calcular el cambio.
6. AL CONFIRMAR EL PEDIDO: Muestra el resumen al cliente y, al final de tu mensaje, incluye la comanda en formato JSON encerrada entre ```json ... ``` con la siguiente estructura:
{{
"tipo_entrega": "domicilio / recoger",
"cliente": "Nombre",
"direccion": "Dirección completa (Zona: Carbonera Norte/Sur)",
"items": [{{"producto": "Nombre", "cantidad": 1, "detalles": "Sin cebolla", "precio_unitario": 75}}],
"metodo_pago": "efectivo / transferencia / tarjeta",
"paga_con": 0,
"cambio": 0,
"total": 75
}}
"""


def registrar_comanda_en_sheets(comanda_data):
    try:
        sheets_service, _ = obtener_servicios_google()
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


# --- CAMBIO 3: GENERAR TICKET LIMPIO PARA COCINA ---
def enviar_ticket_cocina(comanda, telefono_cliente):
    """Genera un mensaje con formato limpio de comanda y lo manda a la cocina."""
    if not NUMERO_COCINA or not EVO_URL or not EVO_APIKEY:
        return

    items_lineas = []
    for item in comanda.get("items", []):
        detalles = f" -> ({item['detalles']})" if item.get("detalles") and item["detalles"] != "N/A" else ""
        items_lineas.append(f"• *{item['cantidad']}x {item['producto']}*{detalles}")
    
    lista_productos = "\n".join(items_lineas)
    
    pago_info = f"Método: *{comanda.get('metodo_pago', 'N/A').upper()}*"
    if str(comanda.get("metodo_pago")).lower() == "efectivo":
        pago_info += f"\nPaga con: ${comanda.get('paga_con', 0)} | Cambio: *${comanda.get('cambio', 0)}*"

    ticket_text = f"""🧾 *NUEVA COMANDA DE COCINA* 🧾
----------------------------------
👤 *Cliente:* {comanda.get('cliente', 'Cliente')}
📱 *Teléfono:* {telefono_cliente}
📍 *Entrega:* {comanda.get('tipo_entrega', 'N/A').upper()}
🏡 *Dirección/Ref:* {comanda.get('direccion', 'Recoge en local')}
----------------------------------
📋 *DETALLE DEL PEDIDO:*
{lista_productos}
----------------------------------
💰 *TOTAL:* ${comanda.get('total', 0)}
💳 {pago_info}
⏰ *Hora:* {datetime.now().strftime('%I:%M %p')}
----------------------------------"""

    send_url = f"{EVO_URL}/message/sendText/{EVO_INSTANCE}"
    headers = {"apikey": EVO_APIKEY, "Content-Type": "application/json"}
    payload = {"number": NUMERO_COCINA, "text": ticket_text}
    try:
        requests.post(send_url, json=payload, headers=headers)
        print(f"📲 Ticket enviado a cocina ({NUMERO_COCINA})")
    except Exception as e:
        print(f"⚠️ Error al enviar ticket a cocina: {e}")


# Configuración de Gemini API Client
MI_API_KEY = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=MI_API_KEY)

sesiones_clientes = {}


def obtener_o_crear_chat(cliente_id):
    if cliente_id not in sesiones_clientes:
        print(f"✨ Creando nueva sesión de chat para el cliente: {cliente_id}")
        prompt_actual = construir_prompt_sistema()
        sesiones_clientes[cliente_id] = client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=prompt_actual, temperature=0.3
            ),
        )
    return sesiones_clientes[cliente_id]


# --- CAMBIO 1: DESCARGAR AUDIO DESDE EVOLUTION API ---
def descargar_audio_evolution(message_keys):
    """Descarga el contenido del audio de Evolution API en formato base64/bytes."""
    if not EVO_URL or not EVO_APIKEY:
        return None
    try:
        url = f"{EVO_URL}/chat/getBase64FromMediaMessage/{EVO_INSTANCE}"
        headers = {"apikey": EVO_APIKEY, "Content-Type": "application/json"}
        payload = {"message": {"key": message_keys}}
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code == 200:
            data = res.json()
            return data.get("base64")
    except Exception as e:
        print(f"⚠️ Error descargando audio de Evolution: {e}")
    return None


def enviar_mensaje_whatsapp(telefono, texto):
    if EVO_URL and EVO_APIKEY:
        send_url = f"{EVO_URL}/message/sendText/{EVO_INSTANCE}"
        headers = {"apikey": EVO_APIKEY, "Content-Type": "application/json"}
        payload = {"number": telefono, "text": texto}
        requests.post(send_url, json=payload, headers=headers)


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
            if "@g.us" in remote_jid:
                return "OK", 200

            telefono = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
            if not telefono:
                return "No phone found", 200

            push_name = incoming_data.get("pushName", "Cliente")
            message_content = incoming_data.get("message", {})

            # 1. DETECTAR Y PROCESAR TEXTO O AUDIO
            contenido_input = []
            
            # Revisar si es audio (audioMessage o pttMessage)
            es_audio = "audioMessage" in message_content or "pttMessage" in message_content
            
            if es_audio:
                print(f"🎙️ Procesando nota de voz de {telefono}...")
                audio_base64 = descargar_audio_evolution(key)
                if audio_base64:
                    import base64
                    audio_bytes = base64.b64decode(audio_base64)
                    # Pasar el archivo de audio directamente a Gemini
                    contenido_input.append(
                        types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type="audio/ogg"  # WhatsApp usa formato ogg/opus
                        )
                    )
                    contenido_input.append("Escucha esta nota de voz del cliente y responde atendiendo su pedido.")
                else:
                    enviar_mensaje_whatsapp(telefono, "Disculpa, no pude escuchar tu audio. ¿Podrías escribírmelo por texto? 🍔")
                    return "EVENT_RECEIVED", 200
            else:
                # Si es texto normal
                texto_usuario = (
                    message_content.get("conversation")
                    or message_content.get("extendedTextMessage", {}).get("text")
                    or ""
                ).strip()
                if not texto_usuario:
                    return "EVENT_RECEIVED", 200
                contenido_input.append(texto_usuario)

            # 2. ENVIAR A GEMINI
            chat_activo = obtener_o_crear_chat(telefono)
            respuesta = chat_activo.send_message(contenido_input)
            texto_respuesta = respuesta.text if respuesta and respuesta.text else ""

            if not texto_respuesta:
                texto_respuesta = "¡Recibido! Dame un segundo para organizarlo. 🍔"

            # 3. VERIFICAR COMANDA JSON Y ENVIAR TICKET DE COCINA
            match = re.search(r"```json\s*(\{.*?\})\s*```", texto_respuesta, re.DOTALL)
            if match:
                json_str = match.group(1)
                try:
                    comanda = json.loads(json_str)
                    if "cliente" not in comanda or comanda["cliente"] == "Nombre":
                        comanda["cliente"] = push_name
                    print("--------------------------------------------------")
                    print(f"🚀 PROCESANDO COMANDA DE {telefono}...")
                    
                    # Guardar en Sheets
                    registrar_comanda_en_sheets(comanda)
                    
                    # Enviar Ticket Limpio a Cocina
                    enviar_ticket_cocina(comanda, telefono)
                    
                    print("--------------------------------------------------\n")
                except json.JSONDecodeError as je:
                    print("Error al decodificar JSON de comanda:", je)

            # 4. LIMPIAR TEXTO Y RESPONDER AL CLIENTE
            texto_para_cliente = re.sub(
                r"```json\s*(\{.*?\})\s*```", "", texto_respuesta, flags=re.DOTALL
            ).strip()

            enviar_mensaje_whatsapp(telefono, texto_para_cliente)

        except Exception as e:
            print("Error crítico en webhook:", str(e))

        return "EVENT_RECEIVED", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
