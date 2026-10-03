import os

import docx
import google.generativeai as genai
import streamlit as st
from google.api_core.exceptions import NotFound

# =====================================================================
# CONSTANTES
# =====================================================================
VERSION_CODIGO = "2026-10-03-a"  # Cambialo en cada commit para confirmar el despliegue

# Orden de preferencia. La app usa el primero que tu API key acepte.
# Podés forzar uno desde Streamlit Secrets con:  MODELO = "nombre-del-modelo"
MODELOS_PREFERIDOS = [
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
]
TEMPERATURA = 0.3  # Más baja = menos invención

# La clave de la clase se puede mover a Secrets con:  CLAVE_CLASE = "tu-clave"
CLAVE_SECRETA = st.secrets.get("CLAVE_CLASE", "NeuroUTN2026")

# =====================================================================
# 1. CONFIGURACIÓN VISUAL
# =====================================================================
st.set_page_config(page_title="Tutor STI - Gestión Universitaria", page_icon="🎓")

# =====================================================================
# 2. PANTALLA DE ACCESO
# =====================================================================
if "acceso_concedido" not in st.session_state:
    st.session_state.acceso_concedido = False

if not st.session_state.acceso_concedido:
    st.image("images.png", width=250)
    st.title("Curso de Inteligencia Artificial Aplicado a la Gestión Universitaria")
    st.subheader("Acceso al Tutor STI")
    st.write("Bienvenido. Por favor, identifícate para comenzar la sesión.")

    clave_ingresada = st.text_input("Contraseña de la clase:", type="password")
    if st.button("Ingresar"):
        if clave_ingresada == CLAVE_SECRETA:
            st.session_state.acceso_concedido = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta. Intenta nuevamente.")
    st.stop()

# =====================================================================
# 3. CONEXIÓN CON LA API
# =====================================================================
st.image("images.png", width=150)
st.title("Tutor Interactivo de Neuroprompting")

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except (KeyError, FileNotFoundError):
    st.error("Falta configurar GEMINI_API_KEY en los Secrets de Streamlit.")
    st.stop()


# =====================================================================
# 4. BASE DE CONOCIMIENTO (se lee una sola vez por reinicio)
# =====================================================================
@st.cache_resource(show_spinner="Cargando materiales del curso...")
def cargar_base_conocimiento():
    """Lee .docx (párrafos y tablas), .md y .pdf de la carpeta del repo.
    Devuelve (texto_total, resumen) donde resumen lista cada archivo y su tamaño."""
    carpeta = os.path.dirname(os.path.abspath(__file__))
    bloques, resumen = [], []

    for nombre in sorted(os.listdir(carpeta)):
        ruta = os.path.join(carpeta, nombre)
        minus = nombre.lower()
        if not os.path.isfile(ruta):
            continue
        if minus.endswith(".docx") and not nombre.startswith("~$"):
            tipo = "docx"
        elif minus.endswith(".md") and minus != "readme.md":
            tipo = "md"
        elif minus.endswith(".pdf"):
            tipo = "pdf"
        else:
            continue

        try:
            if tipo == "docx":
                d = docx.Document(ruta)
                partes = [p.text for p in d.paragraphs if p.text.strip()]
                for tabla in d.tables:
                    for fila in tabla.rows:
                        celdas = [c.text.strip() for c in fila.cells]
                        if any(celdas):
                            partes.append(" | ".join(celdas))
                contenido = "\n".join(partes)
            elif tipo == "md":
                with open(ruta, encoding="utf-8") as f:
                    contenido = f.read()
            else:
                from pypdf import PdfReader  # requiere "pypdf" en requirements.txt

                contenido = "\n".join(
                    (pagina.extract_text() or "") for pagina in PdfReader(ruta).pages
                )
        except Exception as e:
            resumen.append((nombre, f"ERROR: {type(e).__name__}: {e}"))
            continue

        if contenido.strip():
            bloques.append(f"--- DOCUMENTO: {nombre} ---\n{contenido}")
            resumen.append((nombre, f"{len(contenido):,} caracteres"))
        else:
            resumen.append((nombre, "sin texto legible"))

    return "\n\n".join(bloques), resumen


BASE_CONOCIMIENTO, RESUMEN_ARCHIVOS = cargar_base_conocimiento()

INSTRUCCIONES_SISTEMA = f"""
Eres un tutor universitario experto en el Curso de Inteligencia Artificial Aplicado a la Gestión Universitaria.
Tu objetivo es ayudar a los alumnos a comprender la materia.

Reglas de comportamiento:
1. NUNCA digas "Soy un modelo de lenguaje" ni hables como un robot.
2. Sé cálido, empático y usa un tono de profesor universitario accesible.
3. Usa el método socrático: si el alumno se equivoca, no le des la respuesta directa, hazle una pregunta que lo guíe.
4. Mantén tus respuestas concisas y claras.
5. Invita siempre a la reflexión al final de tu mensaje.
6. MUY IMPORTANTE: basa TODAS tus respuestas estrictamente en la "BASE DE CONOCIMIENTOS OFICIAL" que figura abajo.
   Si algo no está en esos documentos, dilo con honestidad ("eso no aparece en los materiales del curso") y no inventes.
   Cuando corresponda, menciona de qué documento o módulo surge lo que explicas.
   Si el alumno pregunta algo fuera de los contenidos del curso, indícale amablemente que se enfoque en la teoría del curso.

BASE DE CONOCIMIENTOS OFICIAL:
{BASE_CONOCIMIENTO}
"""


# =====================================================================
# 5. SELECCIÓN AUTOMÁTICA DE MODELO
# =====================================================================
@st.cache_resource(show_spinner=False)
def obtener_modelos_candidatos():
    """Devuelve los modelos preferidos que tu API key realmente ofrece, en orden."""
    preferidos = list(MODELOS_PREFERIDOS)
    forzado = st.secrets.get("MODELO", None)
    if forzado:
        preferidos = [forzado] + [m for m in preferidos if m != forzado]
    try:
        disponibles = {
            m.name.replace("models/", "")
            for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        }
    except Exception:
        return preferidos  # Si no se puede listar, se prueban igual en orden
    candidatos = [m for m in preferidos if m in disponibles]
    return candidatos or preferidos


def responder(prompt, historial):
    """Prueba los modelos en orden. Ante un 404 pasa al siguiente."""
    ultimo_error = None
    for nombre in obtener_modelos_candidatos():
        try:
            modelo = genai.GenerativeModel(
                nombre,
                system_instruction=INSTRUCCIONES_SISTEMA,
                generation_config={"temperature": TEMPERATURA},
            )
            chat = modelo.start_chat(history=historial)
            respuesta = chat.send_message(prompt)
            return respuesta.text, nombre
        except NotFound as e:
            ultimo_error = e
            continue
    raise ultimo_error if ultimo_error else RuntimeError("No hay modelos disponibles.")


# =====================================================================
# 6. BARRA LATERAL (verificación de lo que está corriendo)
# =====================================================================
with st.sidebar:
    st.caption(f"Versión del código: {VERSION_CODIGO}")
    st.caption("Modelos candidatos: " + ", ".join(obtener_modelos_candidatos()[:3]))
    st.caption("Materiales cargados:")
    if RESUMEN_ARCHIVOS:
        for nombre, estado in RESUMEN_ARCHIVOS:
            st.caption(f"• {nombre} — {estado}")
    else:
        st.caption("• ninguno")
    st.caption(f"Tamaño total de la base: {len(BASE_CONOCIMIENTO):,} caracteres")

# =====================================================================
# 7. MEMORIA DE LA CONVERSACIÓN
# =====================================================================
if "mensajes" not in st.session_state:
    st.session_state.mensajes = [
        {
            "role": "assistant",
            "content": "¡Hola! Qué gusto verte en este espacio de práctica. "
            "¿Por qué concepto del neuroprompting te gustaría que empecemos hoy?",
        }
    ]

for msg in st.session_state.mensajes:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# =====================================================================
# 8. INTERFAZ DE CHAT
# =====================================================================
if prompt := st.chat_input("Escribe tu pregunta o respuesta aquí..."):
    with st.chat_message("user"):
        st.markdown(prompt)

    # Historial para Gemini: sin el saludo inicial (la API exige empezar por "user")
    historial_gemini = []
    for m in st.session_state.mensajes:
        rol = "user" if m["role"] == "user" else "model"
        if not historial_gemini and rol == "model":
            continue
        historial_gemini.append({"role": rol, "parts": [m["content"]]})

    with st.chat_message("assistant"):
        try:
            with st.spinner("Pensando..."):
                texto, modelo_usado = responder(prompt, historial_gemini)
            st.markdown(texto)
            st.caption(f"Modelo: {modelo_usado}")
        except Exception as e:
            st.error(
                "No pude generar la respuesta en este momento. "
                "Intenta de nuevo en unos segundos."
            )
            st.caption(f"Detalle técnico: {type(e).__name__}: {str(e)[:500]}")
            st.stop()

    # Solo se guarda el turno si la respuesta salió bien
    st.session_state.mensajes.append({"role": "user", "content": prompt})
    st.session_state.mensajes.append({"role": "assistant", "content": texto})
