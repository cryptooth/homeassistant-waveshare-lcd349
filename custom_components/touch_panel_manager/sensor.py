"""Touch Panel Manager — Sensor entity'leri.

Config sensor + temperature proxy sensorları.

v0.5:
  - Slot tipi otomatik tespit: domain sensor/binary_sensor → "display", diğerleri → "action"
  - slot_N_main_text: action için label, sensor için canlı değer (birim dahil)
  - slot_N_sub_text:  sensor için label, action için boş
  - Config sensor, slot'larda kullanılan sensor entity'lerini track eder; değişince attribute'lar
    push'lanır → ESPHome canlı günceller.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    ATTR_BUTTONS,
    ATTR_CURRENT_PAGE,
    ATTR_CURRENT_PAGE_TITLE,
    ATTR_INDOOR_TEMP,
    ATTR_OUTDOOR_TEMP,
    ATTR_PAGES_COUNT,
    CONF_BUTTON_ENTITY,
    CONF_BUTTON_LABEL,
    CONF_BUTTONS,
    CONF_INDOOR_TEMP,
    CONF_OUTDOOR_TEMP,
    CONF_PAGE_TITLE,
    CONF_PAGES,
    DEFAULT_ICON,
    DOMAIN,
    DOMAIN_ICONS,
    MAX_BUTTONS,
    SENSOR_DEVICE_CLASS_ICONS,
)

_LOGGER = logging.getLogger(__name__)

# Bu domain'lerde slot "display-only" — değer gösterir, tıklayınca bir şey yapmaz
DISPLAY_DOMAINS = {"sensor", "binary_sensor"}

# State'i olan, sub_text'te durum yazılan action domain'leri
STATEFUL_ACTION_DOMAINS = {"light", "switch", "input_boolean", "fan", "cover", "automation"}


def get_pages(entry: ConfigEntry) -> list[dict]:
    """Multi-page config'i döndür. Legacy single-page (v0.6 ve öncesi) varsa convert et.

    pages: [{"title": str, "buttons": [{"entity_id": ..., "label": ...}, ...]}, ...]
    """
    data = {**entry.data, **entry.options}
    if CONF_PAGES in data and data[CONF_PAGES]:
        return data[CONF_PAGES]
    # Backward compat
    legacy_buttons = data.get(CONF_BUTTONS, [])
    if legacy_buttons:
        return [{CONF_PAGE_TITLE: "Page 1", CONF_BUTTONS: legacy_buttons}]
    return []


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """3 entity yarat: config + outdoor_temp proxy + indoor_temp proxy."""
    async_add_entities([
        TouchPanelConfigSensor(entry),
        TouchPanelTempProxy(entry, kind="outdoor"),
        TouchPanelTempProxy(entry, kind="indoor"),
    ])


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _action_state_text(hass: HomeAssistant, entity_id: str, domain: str) -> str:
    """Sub-text for action slots: On/Off, brightness % for lights.

    Stateless domains (scene/script) → "" (empty, sub line hidden).
    """
    if domain not in STATEFUL_ACTION_DOMAINS:
        return ""

    state_obj = hass.states.get(entity_id)
    if state_obj is None or state_obj.state in ("unknown", "unavailable"):
        return "-"

    s = state_obj.state.lower()
    is_on = s in ("on", "open", "playing", "home")

    # Light + brightness available → "75%"
    if domain == "light" and is_on:
        b = state_obj.attributes.get("brightness")
        if b is not None:
            try:
                pct = round(int(b) / 255 * 100)
                return f"{pct}%"
            except (TypeError, ValueError):
                pass
        return "On"

    # Cover position → "50%"
    if domain == "cover" and is_on:
        pos = state_obj.attributes.get("current_position")
        if pos is not None:
            return f"{int(pos)}%"
        return "Open"

    return "On" if is_on else "Off"


def _icon_for_entity(hass: HomeAssistant, entity_id: str) -> str:
    """Bir entity için uygun MDI glyph'i döndür.

    Sensor için device_class'a bakar, diğerleri için domain'e.
    """
    if not entity_id or "." not in entity_id:
        return DEFAULT_ICON
    domain = entity_id.split(".", 1)[0]

    # Sensor: device_class'a göre
    if domain == "sensor":
        state = hass.states.get(entity_id)
        if state:
            dc = state.attributes.get("device_class")
            if dc and dc in SENSOR_DEVICE_CLASS_ICONS:
                return SENSOR_DEVICE_CLASS_ICONS[dc]
        return SENSOR_DEVICE_CLASS_ICONS.get("temperature", DEFAULT_ICON)  # generic gauge

    return DOMAIN_ICONS.get(domain, DEFAULT_ICON)


def _format_sensor_state(hass: HomeAssistant, entity_id: str) -> str:
    """Bir sensor entity'sinin state'ini ekran-dostu metne çevir.

    "22.3" + "°C" → "22.3°C"
    "on" → "Açık", "off" → "Kapalı"
    bilinmiyorsa "--"
    """
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", ""):
        return "--"

    domain = entity_id.split(".", 1)[0]

    if domain == "binary_sensor":
        return "On" if state.state == "on" else "Off"

    raw = state.state
    # Sayıysa 1 ondalık
    try:
        v = float(raw)
        # Tam sayı görünüyorsa ondalık ekleme
        if v == int(v) and "." not in raw:
            value = str(int(v))
        else:
            value = f"{v:.1f}"
    except (TypeError, ValueError):
        value = raw

    unit = state.attributes.get("unit_of_measurement", "")
    # °C/°F'de boşluk olmadan, %'de olmadan, diğerlerinde boşlukla
    if unit in ("°C", "°F", "°K", "°", "%"):
        return f"{value}{unit}"
    elif unit:
        return f"{value} {unit}"
    return value


# ────────────────────────────────────────────────────────────────────────────
# Config sensor — ESPHome tüm slot bilgilerini buradan okuyacak
# ────────────────────────────────────────────────────────────────────────────

class TouchPanelConfigSensor(SensorEntity):
    """Panel konfigürasyonunu attribute olarak tutan sensor.

    Attribute'lar (ESPHome'un okuyacağı):
      - outdoor_temp, indoor_temp (entity_id string'leri — diagnostic)
      - buttons: [...]  (debug)
      - slot_N_entity   (action dispatch için)
      - slot_N_main_text  (üst satır — label veya sensor değeri)
      - slot_N_sub_text   (alt satır — sensor için label, action için boş)
      - slot_N_type       ("action" veya "display")
    """

    _attr_has_entity_name = True
    _attr_name = "Config"
    _attr_icon = "mdi:cog"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_config"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Touch Panel Manager",
            "model": "Custom Touch Panel",
        }
        self._unsub_listeners: list = []
        self._current_page: int = 0

    @property
    def native_value(self) -> str:
        return "configured"

    @property
    def current_page(self) -> int:
        return self._current_page

    def set_current_page(self, page_index: int) -> None:
        """ESPHome bu metodu service üzerinden çağırır → attribute'lar yeniden push'lanır."""
        pages = get_pages(self._entry)
        if not pages:
            return
        # Clamp
        page_index = max(0, min(page_index, len(pages) - 1))
        if page_index != self._current_page:
            self._current_page = page_index
            self._setup_sensor_tracking()  # yeni sayfanın entity'lerini track et
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Aktif sayfanın slot entity'lerinin state'lerini takip et."""
        await super().async_added_to_hass()
        self._setup_sensor_tracking()

    async def async_will_remove_from_hass(self) -> None:
        self._clear_tracking()

    def _clear_tracking(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    def _setup_sensor_tracking(self) -> None:
        """Aktif sayfadaki TÜM entity'leri track et.

        Sayfa değişince çağrılır → eski listener kaldırılır, yeni sayfa için açılır.
        """
        self._clear_tracking()

        pages = get_pages(self._entry)
        if not pages or self._current_page >= len(pages):
            return

        buttons = pages[self._current_page].get(CONF_BUTTONS, [])
        tracked = [btn.get(CONF_BUTTON_ENTITY) for btn in buttons if btn.get(CONF_BUTTON_ENTITY)]

        if tracked:
            unsub = async_track_state_change_event(
                self.hass, tracked, self._handle_tracked_change
            )
            self._unsub_listeners.append(unsub)

    @callback
    def _handle_tracked_change(self, event: Event) -> None:
        """Track edilen sensor değişti → attribute'lar yeniden push."""
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = {**self._entry.data, **self._entry.options}
        pages = get_pages(self._entry)

        # Current page'i clamp et (sayfa silinmiş olabilir)
        if pages and self._current_page >= len(pages):
            self._current_page = max(0, len(pages) - 1)

        # Aktif sayfanın butonları
        if pages:
            current_page = pages[self._current_page]
            buttons: list[dict[str, str]] = current_page.get(CONF_BUTTONS, [])
            page_title = current_page.get(CONF_PAGE_TITLE, f"Page {self._current_page + 1}")
        else:
            buttons = []
            page_title = ""

        attrs: dict[str, Any] = {
            ATTR_OUTDOOR_TEMP: data.get(CONF_OUTDOOR_TEMP, ""),
            ATTR_INDOOR_TEMP: data.get(CONF_INDOOR_TEMP, ""),
            ATTR_PAGES_COUNT: len(pages),
            ATTR_CURRENT_PAGE: self._current_page,
            ATTR_CURRENT_PAGE_TITLE: page_title,
            ATTR_BUTTONS: buttons,
        }

        for i in range(1, MAX_BUTTONS + 1):
            btn = buttons[i - 1] if i - 1 < len(buttons) else {}
            entity_id = btn.get(CONF_BUTTON_ENTITY, "")
            label = btn.get(CONF_BUTTON_LABEL, "")

            if not entity_id:
                # Boş slot
                attrs[f"slot_{i}_entity"] = ""
                attrs[f"slot_{i}_main_text"] = ""
                attrs[f"slot_{i}_sub_text"] = ""
                attrs[f"slot_{i}_icon"] = ""
                attrs[f"slot_{i}_type"] = "empty"
                continue

            domain = entity_id.split(".", 1)[0]
            attrs[f"slot_{i}_entity"] = entity_id
            attrs[f"slot_{i}_icon"] = _icon_for_entity(self.hass, entity_id)

            if domain in DISPLAY_DOMAINS:
                # Sensor slot: üstte değer, altta label
                attrs[f"slot_{i}_main_text"] = _format_sensor_state(self.hass, entity_id)
                attrs[f"slot_{i}_sub_text"] = label
                attrs[f"slot_{i}_type"] = "display"
            else:
                # Action slot: üstte label, altta state (varsa)
                attrs[f"slot_{i}_main_text"] = label
                attrs[f"slot_{i}_sub_text"] = _action_state_text(self.hass, entity_id, domain)
                attrs[f"slot_{i}_type"] = "action"

        return attrs


# ────────────────────────────────────────────────────────────────────────────
# Temperature proxies (değişmedi)
# ────────────────────────────────────────────────────────────────────────────

class TouchPanelTempProxy(SensorEntity):
    """Config'de seçili dış/iç sıcaklık sensor'ünün değerini proxy eder."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, entry: ConfigEntry, kind: str) -> None:
        self._entry = entry
        self._kind = kind
        self._attr_name = f"{kind.capitalize()} Temp"
        self._attr_unique_id = f"{entry.entry_id}_{kind}_temp"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Touch Panel Manager",
            "model": "Custom Touch Panel",
        }
        self._configured_entity: str | None = None
        self._unsub_track = None

    @property
    def _config_key(self) -> str:
        return CONF_OUTDOOR_TEMP if self._kind == "outdoor" else CONF_INDOOR_TEMP

    def _get_configured(self) -> str | None:
        data = {**self._entry.data, **self._entry.options}
        return data.get(self._config_key) or None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._configured_entity = self._get_configured()
        if self._configured_entity:
            self._unsub_track = async_track_state_change_event(
                self.hass,
                [self._configured_entity],
                self._handle_state_change,
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_track is not None:
            self._unsub_track()
            self._unsub_track = None

    @callback
    def _handle_state_change(self, event: Event) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        if not self._configured_entity:
            return None
        state = self.hass.states.get(self._configured_entity)
        if state is None or state.state in ("unknown", "unavailable", ""):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return self._configured_entity is not None and self.native_value is not None
