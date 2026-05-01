/*
  esp32_emi_generator.ino
  Прошивка ESP32 для генератора ЭМ-помех (MOSFET + индуктивная катушка).
  Принимает команды по UART, управляет PWM и читает ADC с EMI-датчика.

  Команды (Serial @ 115200):
    SET:freq=<Гц>,duty=<0-100>  — установить параметры ШИМ
    STOP                         — выключить генератор
    READ                         — запросить текущее значение с датчика

  Ответы:
    OK:freq=<Гц>,duty=<0-100>
    EMI:<мВ>
    STOPPED
*/

#include "driver/ledc.h"

// ── Пины ──────────────────────────────────────
const int PIN_MOSFET_GATE = 25;   // выход PWM → затвор MOSFET
const int PIN_EMI_SENSOR  = 34;   // ADC вход с катушки-датчика (только вход)
const int PIN_LED         = 2;    // индикаторный светодиод

// ── LEDC (PWM) ────────────────────────────────
const ledc_channel_t PWM_CHANNEL = LEDC_CHANNEL_0;
const ledc_timer_t   PWM_TIMER   = LEDC_TIMER_0;
const ledc_mode_t    PWM_MODE    = LEDC_HIGH_SPEED_MODE;
const int            PWM_BITS    = 10;   // разрядность: 0-1023
const int            PWM_MAX     = (1 << PWM_BITS) - 1;

// ── Состояние ─────────────────────────────────
uint32_t currentFreq = 0;
uint8_t  currentDuty = 0;
bool     running     = false;

// ── EMI-датчик: скользящее среднее ───────────
const int  ADC_SAMPLES    = 32;
const float ADC_REF_MV    = 3300.0f;   // референс 3.3 В
const float ADC_MAX       = 4095.0f;   // 12 бит

float readEMI_mV() {
    long sum = 0;
    for (int i = 0; i < ADC_SAMPLES; i++) {
        sum += analogRead(PIN_EMI_SENSOR);
        delayMicroseconds(200);
    }
    float avg = (float)sum / ADC_SAMPLES;
    return (avg / ADC_MAX) * ADC_REF_MV;
}

// ── Инициализация PWM через LEDC ─────────────
void setupPWM(uint32_t freq, uint8_t dutyPct) {
    ledc_timer_config_t timerConf = {
        .speed_mode      = PWM_MODE,
        .duty_resolution = (ledc_timer_bit_t)PWM_BITS,
        .timer_num       = PWM_TIMER,
        .freq_hz         = (freq > 0) ? freq : 1,
        .clk_cfg         = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timerConf);

    ledc_channel_config_t chanConf = {
        .gpio_num   = PIN_MOSFET_GATE,
        .speed_mode = PWM_MODE,
        .channel    = PWM_CHANNEL,
        .timer_sel  = PWM_TIMER,
        .duty       = (uint32_t)(PWM_MAX * dutyPct / 100),
        .hpoint     = 0,
    };
    ledc_channel_config(&chanConf);
}

void setPWM(uint32_t freq, uint8_t dutyPct) {
    if (freq == 0 || dutyPct == 0) {
        ledc_set_duty(PWM_MODE, PWM_CHANNEL, 0);
        ledc_update_duty(PWM_MODE, PWM_CHANNEL);
        running = false;
        digitalWrite(PIN_LED, LOW);
        return;
    }
    // Обновить частоту таймера
    ledc_set_freq(PWM_MODE, PWM_TIMER, freq);
    // Обновить скважность
    uint32_t duty = (uint32_t)(PWM_MAX * dutyPct / 100);
    ledc_set_duty(PWM_MODE, PWM_CHANNEL, duty);
    ledc_update_duty(PWM_MODE, PWM_CHANNEL);
    running = true;
    digitalWrite(PIN_LED, HIGH);
}

// ── Парсинг команды ───────────────────────────
void parseCommand(String cmd) {
    cmd.trim();

    if (cmd == "STOP") {
        setPWM(0, 0);
        currentFreq = 0;
        currentDuty = 0;
        Serial.println("STOPPED");
        return;
    }

    if (cmd == "READ") {
        float emi = readEMI_mV();
        Serial.print("EMI:");
        Serial.println(emi, 2);
        return;
    }

    if (cmd.startsWith("SET:")) {
        // Формат: SET:freq=1000,duty=50
        int fi = cmd.indexOf("freq=");
        int di = cmd.indexOf("duty=");
        if (fi < 0 || di < 0) {
            Serial.println("ERR:bad_format");
            return;
        }
        uint32_t freq = (uint32_t)cmd.substring(fi + 5, cmd.indexOf(',', fi)).toInt();
        uint8_t  duty = (uint8_t)cmd.substring(di + 5).toInt();

        // Ограничения безопасности
        freq = constrain(freq, 1, 100000);
        duty = constrain(duty, 0, 90);   // max 90% — защита MOSFET

        currentFreq = freq;
        currentDuty = duty;
        setupPWM(freq, duty);
        setPWM(freq, duty);

        Serial.print("OK:freq=");
        Serial.print(freq);
        Serial.print(",duty=");
        Serial.println(duty);
        return;
    }

    Serial.println("ERR:unknown_cmd");
}

// ── Фоновая отправка EMI каждые 500 мс ───────
unsigned long lastEMISend = 0;

void setup() {
    Serial.begin(115200);
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);   // диапазон 0–3.3 В

    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, LOW);

    // Инициализировать PWM с нулевой скважностью
    setupPWM(50, 0);
    Serial.println("READY");
}

void loop() {
    // Чтение команд из Serial
    if (Serial.available()) {
        String cmd = Serial.readStringUntil('\n');
        parseCommand(cmd);
    }

    // Периодическая отправка данных датчика
    if (millis() - lastEMISend >= 500) {
        lastEMISend = millis();
        float emi = readEMI_mV();
        Serial.print("EMI:");
        Serial.println(emi, 2);
    }
}
