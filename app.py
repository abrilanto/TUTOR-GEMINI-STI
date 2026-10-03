import streamlit as st
import google.generativeai as genai
import docx
import os

# 1. CONFIGURACIÓN VISUAL
st.set_page_config(page_title="Tutor STI - Gestión Universitaria", page_icon="🎓")

# 2. PANTALLA DE ACCESO (Seguridad)
CLAVE_SECRETA = "NeuroUTN2026" # Puedes cambiar esto luego si quieres

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
    

# 3. CONFIGURACIÓN DE LA IA Y MEMORIA
st.image("images.png", width=150)
st.title("Tutor Interactivo de Neuroprompting")

# Conectar con la API Key guardada en Streamlit
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except:
    st.warning("Falta configurar la API Key en Streamlit. Lo haremos en el próximo paso.")
    st.stop()

# Instrucciones de comportamiento (Neuroprompting)
INSTRUCCIONES_SISTEMA = """
Eres un tutor universitario experto en el Curso de Inteligencia Artificial Aplicado a la Gestión Universitaria.
Tu objetivo es ayudar a los alumnos a comprender el neuroprompting.
Reglas de comportamiento:
1. NUNCA digas "Soy un modelo de lenguaje" ni hables como un robot.
2. Sé cálido, empático y usa un tono de profesor universitario accesible.
3. Usa el método socrático: si el alumno se equivoca, no le des la respuesta directa, hazle una pregunta que lo guíe.
4. Mantén tus respuestas concisas y claras.
5. Invita siempre a la reflexión al final de tu mensaje.
"""

# Inicializar el modelo
modelo = genai.GenerativeModel("gemini-flash-latest", system_instruction=INSTRUCCIONES_SISTEMA)

# Memoria de la conversación
if "mensajes" not in st.session_state:
    st.session_state.mensajes = []
    # Saludo inicial proactivo
    st.session_state.mensajes.append({"role": "assistant", "content": "¡Hola! Qué gusto verte en este espacio de práctica. ¿Por qué concepto del neuroprompting te gustaría que empecemos hoy?"})

# Mostrar historial
for msg in st.session_state.mensajes:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 4. INTERFAZ DE CHAT
if prompt := st.chat_input("Escribe tu pregunta o respuesta aquí..."):
    # Mostrar lo que escribió el usuario
    st.session_state.mensajes.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Generar respuesta de la IA
    with st.chat_message("assistant"):
        historial_gemini = [{"role": m["role"] if m["role"] == "user" else "model", "parts": [m["content"]]} for m in st.session_state.mensajes[:-1]]
        chat = modelo.start_chat(history=historial_gemini)
        respuesta = chat.send_message(prompt)
        st.markdown(respuesta.text)
    
    # Guardar respuesta
    st.session_state.mensajes.append({"role": "assistant", "content": respuesta.text})
