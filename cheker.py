import logging
import requests
import datetime
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os

# Configuración
TELEGRAM_TOKEN = "7687310799:AAFxqEFh-mnC6slPebxI1xEbR3dauKEnVmk"
FD_API_KEY = "7b8f1d62b59c4cfc97e79dd064d9d956"
FD_HEADERS = {"X-Auth-Token": FD_API_KEY}
FD_BASE_URL = "https://api.football-data.org/v4"
USER_ID = 1865970861  # Tu chat ID

# Memoria de usuarios y logging
user_leagues = {}  # Guarda la liga seleccionada por usuario
logging.basicConfig(level=logging.INFO)

# Función para enviar mensajes largos divididos
MAX_MESSAGE_LENGTH = 4096

async def send_long_message(chat_id, text, bot):
    """Envía un mensaje largo dividido en partes si es necesario."""
    for i in range(0, len(text), MAX_MESSAGE_LENGTH):
        await bot.send_message(chat_id=chat_id, text=text[i:i + MAX_MESSAGE_LENGTH], parse_mode="Markdown")

# Comandos del bot

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ¡Hola! Usa /ligas para ver las ligas disponibles.")

async def ligas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra las ligas disponibles."""
    r = requests.get(f"{FD_BASE_URL}/competitions", headers=FD_HEADERS)
    if r.status_code != 200:
        await update.message.reply_text("⚠️ No pude obtener las ligas.")
        return

    data = r.json()
    ligas = [c['name'] for c in data['competitions'] if c['plan'] == "TIER_ONE"]
    mensaje = "🏆 *Ligas disponibles:*\n\n" + "\n".join(f"- {liga}" for liga in ligas)

    await send_long_message(update.message.chat_id, mensaje, context.bot)

async def elegir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite al usuario elegir una liga."""
    if not context.args:
        await update.message.reply_text("❗️ Usa el comando así: /elegir Premier League")
        return

    liga_nombre = " ".join(context.args).lower()
    r = requests.get(f"{FD_BASE_URL}/competitions", headers=FD_HEADERS)
    data = r.json()
    ligas = {c["name"].lower(): c["code"] for c in data["competitions"] if c["plan"] == "TIER_ONE"}

    if liga_nombre not in ligas:
        await update.message.reply_text("❌ Liga no encontrada. Usa /ligas para ver las disponibles.")
        return

    user_id = update.message.chat_id
    user_leagues[user_id] = ligas[liga_nombre]
    await update.message.reply_text(f"✅ Liga *{liga_nombre.title()}* seleccionada.", parse_mode="Markdown")

async def entrenar_modelo(codigo: str):
    """Entrena el modelo XGBoost con datos históricos de la liga."""
    r = requests.get(f"{FD_BASE_URL}/competitions/{codigo}/matches?status=FINISHED&limit=100", headers=FD_HEADERS)
    data = r.json()

    # Datos y resultados
    datos, resultados = [], []

    for match in data.get("matches", []):
        score = match["score"]["fullTime"]
        if score["home"] is None or score["away"] is None:
            continue

        home, away = match["homeTeam"]["name"], match["awayTeam"]["name"]
        datos.append([home, away])

        if score["home"] > score["away"]:
            resultados.append("home")
        elif score["away"] > score["home"]:
            resultados.append("away")
        else:
            resultados.append("draw")

    if not datos:
        return None

    # Crear el dataframe
    df = pd.DataFrame(datos, columns=["home", "away"])
    df["result"] = resultados

    # Convertir las etiquetas de 'result' a números: home=0, away=1, draw=2
    df["result"] = df["result"].map({"home": 0, "away": 1, "draw": 2})

    # Codificar los equipos (one-hot encoding)
    df_encoded = pd.get_dummies(df[["home", "away"]])

    # Entrenar el modelo XGBoost
    model = xgb.XGBClassifier(objective='multi:softmax', num_class=3)
    model.fit(df_encoded, df["result"])

    return model, df_encoded, df

async def pronostico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera el pronóstico de los partidos futuros usando el modelo entrenado."""
    user_id = update.message.chat_id
    if user_id not in user_leagues:
        await update.message.reply_text("❗️ Primero debes elegir una liga con /elegir")
        return

    codigo = user_leagues[user_id]
    await update.message.reply_text("📊 Obteniendo datos reales de partidos anteriores...")

    # Entrenar el modelo XGBoost
    model, df_encoded, df = await entrenar_modelo(codigo)
    if model is None:
        await update.message.reply_text("⚠️ No se encontraron suficientes datos para entrenar.")
        return

    await update.message.reply_text("📅 Obteniendo próximos partidos...")

    # Obtener partidos programados para hoy
    hoy = datetime.datetime.utcnow().date().isoformat()
    r2 = requests.get(f"{FD_BASE_URL}/competitions/{codigo}/matches?status=SCHEDULED&dateFrom={hoy}&dateTo={hoy}", headers=FD_HEADERS)
    future = r2.json().get("matches", [])

    if not future:
        await update.message.reply_text("⚠️ No hay partidos programados para hoy.")
        return

    predicciones = []

    for match in future:
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        date = match["utcDate"][:10]
        hora = match["utcDate"][11:16]  # Hora en formato HH:mm

        fila = pd.DataFrame([[home, away]], columns=["home", "away"])
        fila_encoded = pd.get_dummies(fila).reindex(columns=df_encoded.columns, fill_value=0)

        # Predicción del resultado
        ganador = model.predict(fila_encoded)[0]
        proba = model.predict_proba(fila_encoded)[0]
        goles_local = round(proba[model.classes_.tolist().index(0)] * 3)
        goles_visitante = round(proba[model.classes_.tolist().index(1)] * 3)

        # Añadir el pronóstico del partido
        predicciones.append(
            f"📅 {date} | {hora} | *{home}* vs *{away}*\n"
            f"👉 Gana: *{['Home', 'Away', 'Draw'][ganador]}*\n"
            f"⚽️ Goles estimados: {home} {goles_local} - {goles_visitante} {away}\n"
        )

    # Enviar los pronósticos por separado
    for prediccion in predicciones:
        await update.message.reply_text(prediccion)

# Main
def main():
    # Iniciar la aplicación de Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ligas", ligas))
    app.add_handler(CommandHandler("elegir", elegir))
    app.add_handler(CommandHandler("pronostico", pronostico))

    print("✅ Bot iniciado. Esperando comandos...")
    app.run_polling()

if __name__ == "__main__":
    main()
