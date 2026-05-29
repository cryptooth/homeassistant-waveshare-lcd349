"""Constants for Touch Panel Manager."""

DOMAIN = "touch_panel_manager"

# Config keys (saved in ConfigEntry.data / options)
CONF_NAME = "name"
CONF_OUTDOOR_TEMP = "outdoor_temp"
CONF_INDOOR_TEMP = "indoor_temp"
CONF_BUTTONS = "buttons"           # legacy single-page (v0.6 and earlier)
CONF_PAGES = "pages"               # multi-page (v0.7+)
CONF_PAGE_TITLE = "title"

# Per-button keys
CONF_BUTTON_ENTITY = "entity_id"
CONF_BUTTON_LABEL = "label"

# Sensor entity attributes (ESPHome cihazı bunlara bakacak)
ATTR_BUTTONS = "buttons"
ATTR_OUTDOOR_TEMP = "outdoor_temp"
ATTR_INDOOR_TEMP = "indoor_temp"
ATTR_PAGES_COUNT = "pages_count"
ATTR_CURRENT_PAGE = "current_page"
ATTR_CURRENT_PAGE_TITLE = "current_page_title"

# Defaults
DEFAULT_NAME = "Touch Panel"
MAX_BUTTONS = 8  # form'da gösterilecek slot sayısı (boş bırakılanlar elenir)

# Buton seçici için desteklenen entity domain'leri
# Action tipleri: panel_action ile toggle/turn_on
# Display tipleri (sensor, binary_sensor): değer/state gösterilir, tıklamada işlem yok
SUPPORTED_BUTTON_DOMAINS = [
    "light", "switch", "scene", "script", "input_boolean", "automation",
    "fan", "cover", "media_player",
    "sensor", "binary_sensor",  # display-only
]

# MDI (Material Design Icons) glyph kodları — domain → unicode codepoint
# ESPHome tarafındaki font_icons glyphs: listesi bunlarla eşleşmeli.
DOMAIN_ICONS = {
    "light":         "\U000F0335",  # mdi-lightbulb
    "switch":        "\U000F06D5",  # mdi-toggle-switch-outline
    "scene":         "\U000F040A",  # mdi-play-circle-outline
    "script":        "\U000F0BC1",  # mdi-script-text-outline
    "input_boolean": "\U000F0521",  # mdi-toggle-switch
    "automation":    "\U000F0A22",  # mdi-robot
    "fan":           "\U000F0210",  # mdi-fan
    "cover":         "\U000F1486",  # mdi-window-shutter
    "media_player":  "\U000F040A",  # mdi-play-circle-outline
    "binary_sensor": "\U000F0D91",  # mdi-motion-sensor
}

# Sensor için device_class → glyph
SENSOR_DEVICE_CLASS_ICONS = {
    "temperature": "\U000F050F",   # mdi-thermometer
    "humidity":    "\U000F058C",   # mdi-water-percent
    "battery":     "\U000F0079",   # mdi-battery
    "power":       "\U000F0AF6",   # mdi-flash
    "energy":      "\U000F0274",   # mdi-lightning-bolt
    "illuminance": "\U000F0335",   # mdi-lightbulb (ışık seviyesi)
    "pressure":    "\U000F0260",   # mdi-gauge
    "voltage":     "\U000F0AF6",   # mdi-flash
    "current":     "\U000F0AF6",   # mdi-flash
}

# Fallback (domain veya device_class eşleşmezse)
DEFAULT_ICON = "\U000F0625"  # mdi-help-circle-outline
