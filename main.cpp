/*
  osu! keypad — Waveshare RP2040-Zero

  Arduino IDE:
    Board: "Waveshare RP2040-Zero" (Raspberry Pi Pico/RP2040 by Earle Philhower)
    Tools -> USB Stack: Adafruit TinyUSB
  Library Manager: install "Adafruit TinyUSB Library".

  The board enumerates as a composite USB CDC + HID keyboard device.  The HID
  descriptor has a 1 ms endpoint interval; the selected HZ value is the
  software report scheduler interval.  USB Full Speed cannot advertise 750 Hz
  exactly, but the 750 Hz setting is honoured by this scheduler (1333 us).
*/

#include <Arduino.h>
#include <Adafruit_TinyUSB.h>
#include <Adafruit_NeoPixel.h>
#include <EEPROM.h>
#include <string.h>

constexpr uint8_t KEY_PINS[3] = {0, 1, 2};
constexpr uint8_t LED_PIN = 16;
constexpr uint16_t EEPROM_BYTES = 256;
constexpr uint32_t CONFIG_MAGIC = 0x4F53554B; // "OSUK"
constexpr uint8_t CONFIG_VERSION = 1;

// A standard boot-protocol keyboard report descriptor.
uint8_t const hid_report_descriptor[] = { TUD_HID_REPORT_DESC_KEYBOARD() };
Adafruit_USBD_HID usb_hid;
Adafruit_NeoPixel led(1, LED_PIN, NEO_GRB + NEO_KHZ800);

struct __attribute__((packed)) Config {
  uint32_t magic;
  uint8_t version;
  uint8_t keys[3];             // printable ASCII character for each button
  uint16_t pollHz;             // 125, 250, 500, 750 or 1000
  uint8_t debounceMs;          // 0..10; 0 is direct pin reading
  uint8_t red, green, blue;
  uint16_t checksum;
};

Config config;
bool physicalPressed[3] = {false, false, false};
bool debouncedPressed[3] = {false, false, false};
uint32_t lastAcceptedChangeUs[3] = {0, 0, 0};
bool keyboardDirty = true;
uint32_t nextReportUs = 0;

char commandBuffer[160];
uint8_t commandLength = 0;

uint16_t calculateChecksum(const Config &value) {
  const uint8_t *bytes = reinterpret_cast<const uint8_t *>(&value);
  uint16_t sum = 0;
  // Exclude checksum itself, so EEPROM corruption is detected at boot.
  for (size_t i = 0; i < sizeof(Config) - sizeof(value.checksum); ++i) sum += bytes[i];
  return sum;
}

bool isAllowedHz(uint16_t hz) {
  return hz == 125 || hz == 250 || hz == 500 || hz == 750 || hz == 1000;
}

bool isValidConfig(const Config &value) {
  return value.magic == CONFIG_MAGIC && value.version == CONFIG_VERSION &&
         isAllowedHz(value.pollHz) && value.debounceMs <= 10 &&
         value.checksum == calculateChecksum(value);
}

void useDefaults() {
  config.magic = CONFIG_MAGIC;
  config.version = CONFIG_VERSION;
  config.keys[0] = 'z';
  config.keys[1] = 'x';
  config.keys[2] = 'c';
  config.pollHz = 1000;
  config.debounceMs = 0;
  config.red = 0;
  config.green = 80;
  config.blue = 255;
  config.checksum = calculateChecksum(config);
}

void saveConfig() {
  config.magic = CONFIG_MAGIC;
  config.version = CONFIG_VERSION;
  config.checksum = calculateChecksum(config);
  EEPROM.put(0, config);
  EEPROM.commit();
}

void applyLed() {
  led.setPixelColor(0, led.Color(config.red, config.green, config.blue));
  led.show();
}

// Converts printable US keyboard ASCII into a HID usage and modifier byte.
// The desktop application deliberately sends printable ASCII only.
bool asciiToHid(uint8_t ascii, uint8_t &usage, uint8_t &modifier) {
  modifier = 0;
  if (ascii >= 'a' && ascii <= 'z') { usage = HID_KEY_A + ascii - 'a'; return true; }
  if (ascii >= 'A' && ascii <= 'Z') { usage = HID_KEY_A + ascii - 'A'; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true; }
  if (ascii >= '1' && ascii <= '9') { usage = HID_KEY_1 + ascii - '1'; return true; }
  if (ascii == '0') { usage = HID_KEY_0; return true; }

  switch (ascii) {
    case ' ': usage = HID_KEY_SPACE; return true;
    case '-': usage = HID_KEY_MINUS; return true; case '_': usage = HID_KEY_MINUS; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '=': usage = HID_KEY_EQUAL; return true; case '+': usage = HID_KEY_EQUAL; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '[': usage = HID_KEY_BRACKET_LEFT; return true; case '{': usage = HID_KEY_BRACKET_LEFT; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case ']': usage = HID_KEY_BRACKET_RIGHT; return true; case '}': usage = HID_KEY_BRACKET_RIGHT; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '\\': usage = HID_KEY_BACKSLASH; return true; case '|': usage = HID_KEY_BACKSLASH; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case ';': usage = HID_KEY_SEMICOLON; return true; case ':': usage = HID_KEY_SEMICOLON; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '\'': usage = HID_KEY_APOSTROPHE; return true; case '"': usage = HID_KEY_APOSTROPHE; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '`': usage = HID_KEY_GRAVE; return true; case '~': usage = HID_KEY_GRAVE; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case ',': usage = HID_KEY_COMMA; return true; case '<': usage = HID_KEY_COMMA; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '.': usage = HID_KEY_PERIOD; return true; case '>': usage = HID_KEY_PERIOD; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '/': usage = HID_KEY_SLASH; return true; case '?': usage = HID_KEY_SLASH; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '!': usage = HID_KEY_1; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '@': usage = HID_KEY_2; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '#': usage = HID_KEY_3; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '$': usage = HID_KEY_4; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '%': usage = HID_KEY_5; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '^': usage = HID_KEY_6; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '&': usage = HID_KEY_7; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '*': usage = HID_KEY_8; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case '(': usage = HID_KEY_9; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
    case ')': usage = HID_KEY_0; modifier = KEYBOARD_MODIFIER_LEFTSHIFT; return true;
  }
  return false;
}

void scanKeys() {
  const uint32_t now = micros();
  for (uint8_t i = 0; i < 3; ++i) {
    const bool rawPressed = digitalRead(KEY_PINS[i]) == LOW;
    if (rawPressed == physicalPressed[i]) continue;
    physicalPressed[i] = rawPressed;

    // Eager debounce: accept the first edge immediately, then ignore further
    // edges for the configured guard time.  At 0 ms every pin edge is direct.
    if (config.debounceMs == 0 ||
        static_cast<uint32_t>(now - lastAcceptedChangeUs[i]) >= config.debounceMs * 1000UL) {
      lastAcceptedChangeUs[i] = now;
      if (debouncedPressed[i] != rawPressed) {
        debouncedPressed[i] = rawPressed;
        keyboardDirty = true;
      }
    }
  }
}

void sendKeyboardReport() {
  if (!keyboardDirty || !usb_hid.ready()) return;
  hid_keyboard_report_t report = {};
  for (uint8_t i = 0; i < 3; ++i) {
    if (!debouncedPressed[i]) continue;
    uint8_t usage, modifier;
    if (asciiToHid(config.keys[i], usage, modifier)) {
      report.keycode[i] = usage;
      report.modifier |= modifier;
    }
  }
  usb_hid.sendReport(0, &report, sizeof(report));
  keyboardDirty = false;
}

void printConfig() {
  Serial.printf("CFG:K1=%u,K2=%u,K3=%u,HZ=%u,DEB=%u,RGB=%u,%u,%u\\n",
                config.keys[0], config.keys[1], config.keys[2], config.pollHz,
                config.debounceMs, config.red, config.green, config.blue);
}

bool parseUnsigned(const char *text, unsigned long &result) {
  if (*text == '\0') return false;
  char *end;
  result = strtoul(text, &end, 10);
  return *end == '\0';
}

void processCommand(char *line) {
  if (strcmp(line, "GET_CONFIG") == 0) { printConfig(); return; }
  if (strcmp(line, "PING") == 0) { Serial.println("PONG"); return; }
  if (strncmp(line, "SET:", 4) != 0) { Serial.println("ERR:UNKNOWN_COMMAND"); return; }

  Config updated = config;
  bool rgbSet = false;
  char *context = nullptr;
  for (char *token = strtok_r(line + 4, ",", &context); token; token = strtok_r(nullptr, ",", &context)) {
    unsigned long value;
    if (strncmp(token, "K1=", 3) == 0 && parseUnsigned(token + 3, value) && value >= 32 && value <= 126) updated.keys[0] = value;
    else if (strncmp(token, "K2=", 3) == 0 && parseUnsigned(token + 3, value) && value >= 32 && value <= 126) updated.keys[1] = value;
    else if (strncmp(token, "K3=", 3) == 0 && parseUnsigned(token + 3, value) && value >= 32 && value <= 126) updated.keys[2] = value;
    else if (strncmp(token, "HZ=", 3) == 0 && parseUnsigned(token + 3, value) && isAllowedHz(value)) updated.pollHz = value;
    else if (strncmp(token, "DEB=", 4) == 0 && parseUnsigned(token + 4, value) && value <= 10) updated.debounceMs = value;
    else if (strncmp(token, "RGB=", 4) == 0) {
      unsigned int r, g, b;
      // RGB has commas, so consume its two continuation tokens explicitly.
      char *greenToken = strtok_r(nullptr, ",", &context);
      char *blueToken = strtok_r(nullptr, ",", &context);
      if (sscanf(token + 4, "%u", &r) != 1 || !greenToken || !blueToken ||
          sscanf(greenToken, "%u", &g) != 1 || sscanf(blueToken, "%u", &b) != 1 ||
          r > 255 || g > 255 || b > 255) { Serial.println("ERR:BAD_RGB"); return; }
      updated.red = r; updated.green = g; updated.blue = b; rgbSet = true;
    } else { Serial.println("ERR:BAD_VALUE"); return; }
  }
  (void)rgbSet;
  config = updated;
  saveConfig();
  applyLed();
  keyboardDirty = true;
  Serial.println("OK");
  printConfig();
}

void readSerialNonBlocking() {
  while (Serial.available() > 0) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      commandBuffer[commandLength] = '\0';
      if (commandLength) processCommand(commandBuffer);
      commandLength = 0;
    } else if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = c;
    } else {
      commandLength = 0; // discard oversized command safely
      Serial.println("ERR:COMMAND_TOO_LONG");
    }
  }
}

void setup() {
  for (uint8_t pin : KEY_PINS) pinMode(pin, INPUT_PULLUP);
  led.begin();
  led.clear();
  led.show();

  EEPROM.begin(EEPROM_BYTES);
  EEPROM.get(0, config);
  if (!isValidConfig(config)) { useDefaults(); saveConfig(); }
  applyLed();

  usb_hid.setPollInterval(1); // endpoint descriptor: 1 ms (maximum FS HID rate)
  usb_hid.setReportDescriptor(hid_report_descriptor, sizeof(hid_report_descriptor));
  usb_hid.begin();
  Serial.begin(115200);
  const uint32_t now = micros();
  for (uint8_t i = 0; i < 3; ++i) {
    // Establish an accurate initial state; a held button at boot must not be
    // lost merely because the debounce guard interval has not elapsed yet.
    physicalPressed[i] = digitalRead(KEY_PINS[i]) == LOW;
    debouncedPressed[i] = physicalPressed[i];
    lastAcceptedChangeUs[i] = now - config.debounceMs * 1000UL;
  }
  nextReportUs = micros();
}

void loop() {
  scanKeys();
  readSerialNonBlocking();
  const uint32_t now = micros();
  const uint32_t interval = 1000000UL / config.pollHz;
  if (static_cast<int32_t>(now - nextReportUs) >= 0) {
    nextReportUs = now + interval; // no blocking delay
    sendKeyboardReport();
  }
}
