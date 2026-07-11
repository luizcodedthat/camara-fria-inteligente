#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <time.h>
#include <OneWire.h>
#include <DallasTemperature.h>

const char* WIFI_SSID     = "XXXXXXXXXXXXXXX";
const char* WIFI_PASSWORD = "XXXXXXXXXXXXXXX";
const char* NTP_SERVER    = "pool.ntp.org";
const long  GMT_OFFSET    = -10800;
const int   DST_OFFSET    = 0;

const char* API_URL   = "http://SEU_IP:8000/api/v1/esp32/reading";
const char* DEVICE_ID = "esp32-camara-fria-01";
const unsigned long HTTP_TIMEOUT_MS = 5000;

#define PIN_DS18B20     4
#define PIN_TRIG_HCSR04 22
#define PIN_ECHO_HCSR04 23

const unsigned long HCSR04_TIMEOUT_US = 30000;
const float DISTANCIA_PORTA_ABERTA_CM = 5.0;

OneWire oneWire(PIN_DS18B20);
DallasTemperature dsSensors(&oneWire);

struct Leitura {
    String timestamp;
    float  temperaturaDS18B20;
    int    portaAberta;
    bool   erroDS18B20;
    bool   erroDistancia;
};

std::vector<Leitura> buffer;
int ultimoEstadoPortaValido = 0;

void setupWiFi();
void setupTime();
void setupSensors();
Leitura readSensors();
float medirDistanciaCM();
String getTimestamp();
void printDataToSerial(const Leitura& leitura);
void enviarLeituraHTTP(const Leitura& leitura);

void setup() {
    Serial.begin(115200);
    while (!Serial) { delay(10); }

    Serial.println("\n--- Iniciando Sistema de Coleta de Dados ---");

    setupSensors();
    setupWiFi();
    setupTime();

    Serial.println("Sistema inicializado com sucesso.");
}

void loop() {
    static unsigned long lastReadTime = 0;
    const unsigned long READ_INTERVAL = 5000;

    if (millis() - lastReadTime >= READ_INTERVAL) {
        lastReadTime = millis();

        Leitura leitura = readSensors();
        printDataToSerial(leitura);
        buffer.push_back(leitura);
        enviarLeituraHTTP(leitura);
    }
}

void setupWiFi() {
    Serial.print("Conectando ao Wi-Fi: ");
    Serial.println(WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int tentativas = 0;
    while (WiFi.status() != WL_CONNECTED && tentativas < 20) {
        delay(500);
        Serial.print(".");
        tentativas++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWi-Fi Conectado! Relógio será sincronizado via NTP.");
    } else {
        Serial.println("\nWi-Fi falhou. Timestamps usarão tempo desde o boot.");
    }
}

void setupTime() {
    if (WiFi.status() != WL_CONNECTED) return;
    configTime(GMT_OFFSET, DST_OFFSET, NTP_SERVER);
    struct tm timeinfo;
    if (getLocalTime(&timeinfo)) Serial.println("Relógio sincronizado.");
}

String getTimestamp() {
    struct tm timeinfo;
    if (!getLocalTime(&timeinfo)) return "Offline_" + String(millis() / 1000) + "s";
    char buf[25];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &timeinfo);
    return String(buf);
}

void setupSensors() {
    dsSensors.begin();
    pinMode(PIN_TRIG_HCSR04, OUTPUT);
    pinMode(PIN_ECHO_HCSR04, INPUT);
    digitalWrite(PIN_TRIG_HCSR04, LOW);
}

float medirDistanciaCM() {
    digitalWrite(PIN_TRIG_HCSR04, LOW);
    delayMicroseconds(2);
    digitalWrite(PIN_TRIG_HCSR04, HIGH);
    delayMicroseconds(10);
    digitalWrite(PIN_TRIG_HCSR04, LOW);

    unsigned long duracao = pulseIn(PIN_ECHO_HCSR04, HIGH, HCSR04_TIMEOUT_US);
    if (duracao == 0) return -1.0;

    return (duracao * 0.0343f) / 2.0f;
}

Leitura readSensors() {
    Leitura leitura;
    leitura.timestamp = getTimestamp();

    dsSensors.requestTemperatures();
    leitura.temperaturaDS18B20 = dsSensors.getTempCByIndex(0);
    leitura.erroDS18B20 = (leitura.temperaturaDS18B20 == DEVICE_DISCONNECTED_C);

    float distancia = medirDistanciaCM();
    leitura.erroDistancia = (distancia < 0);
    leitura.portaAberta = (!leitura.erroDistancia && distancia > DISTANCIA_PORTA_ABERTA_CM) ? 1 : 0;

    if (!leitura.erroDistancia) {
        ultimoEstadoPortaValido = leitura.portaAberta;
    }

    return leitura;
}

void printDataToSerial(const Leitura& leitura) {
    Serial.print("["); Serial.print(leitura.timestamp); Serial.print("] ");
    Serial.print("DS18B20: ");
    if (leitura.erroDS18B20) Serial.print("ERRO");
    else { Serial.print(leitura.temperaturaDS18B20, 1); Serial.print(" °C"); }

    Serial.print(" | Porta: ");
    if (leitura.erroDistancia) Serial.print("ERRO");
    else Serial.print(leitura.portaAberta ? "ABERTA" : "FECHADA");

    Serial.println();
}

void enviarLeituraHTTP(const Leitura& leitura) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("Wi-Fi offline — leitura não enviada via HTTP (mantida só no buffer local).");
        return;
    }

    if (leitura.erroDS18B20) {
        Serial.println("DS18B20 com erro — leitura não enviada (temperature_internal obrigatório).");
        return;
    }

    int portaParaEnviar = leitura.erroDistancia ? ultimoEstadoPortaValido : leitura.portaAberta;
    const char* doorState = portaParaEnviar ? "open" : "closed";

    char payload[160];
    snprintf(
        payload, sizeof(payload),
        "{\"device_id\":\"%s\",\"temperature_internal\":%.2f,\"door_state\":\"%s\"}",
        DEVICE_ID, leitura.temperaturaDS18B20, doorState
    );

    HTTPClient http;
    http.begin(API_URL);
    http.addHeader("Content-Type", "application/json");
    http.setTimeout(HTTP_TIMEOUT_MS);

    int statusCode = http.POST((uint8_t*)payload, strlen(payload));

    if (statusCode > 0) {
        Serial.print("POST /esp32/reading -> HTTP ");
        Serial.print(statusCode);
        if (statusCode != 200 && statusCode != 201) {
            Serial.print(" | resposta: ");
            Serial.println(http.getString());
        } else {
            Serial.println();
        }
    } else {
        Serial.print("Falha na requisição HTTP: ");
        Serial.println(http.errorToString(statusCode));
    }

    http.end();
}