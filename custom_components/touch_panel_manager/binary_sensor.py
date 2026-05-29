"""Touch Panel Manager — Slot state binary sensors (page-aware).

Each slot's binary sensor reflects the on/off state of the entity assigned to
that slot ON THE CURRENT PAGE. When the device flips pages, the config sensor
pushes a state change; binary sensors re-subscribe to the new entities.
"""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_BUTTON_ENTITY,
    CONF_BUTTONS,
    DOMAIN,
    MAX_BUTTONS,
)
from .sensor import get_pages  # paylaşılan helper

_LOGGER = logging.getLogger(__name__)

ON_STATEFUL_DOMAINS = {
    "light", "switch", "input_boolean", "fan", "media_player",
    "automation", "binary_sensor",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = [TouchPanelSlotStateProxy(entry, i) for i in range(1, MAX_BUTTONS + 1)]
    async_add_entities(entities)


class TouchPanelSlotStateProxy(BinarySensorEntity):
    """Aktif sayfanın slot N entity'sinin on/off state'ini proxy'ler."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, slot_index: int) -> None:
        self._entry = entry
        self._slot_index = slot_index
        self._attr_name = f"Slot {slot_index} State"
        self._attr_unique_id = f"{entry.entry_id}_slot_{slot_index}_state"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Touch Panel Manager",
            "model": "Custom Touch Panel",
        }
        self._tracked_entity: str | None = None
        self._unsub_entity_track = None
        self._unsub_config_track = None

    def _get_config_sensor_entity_id(self) -> str:
        """sensor.<panel>_config entity'sinin ID'sini bulmak için entity registry'ye bak."""
        # Unique id pattern'ından entity ID'yi bul
        from homeassistant.helpers import entity_registry as er
        reg = er.async_get(self.hass)
        config_unique_id = f"{self._entry.entry_id}_config"
        for entity_id, e in reg.entities.items():
            if e.unique_id == config_unique_id and e.platform == DOMAIN:
                return entity_id
        return ""

    def _get_current_page_slot_entity(self) -> str | None:
        """Aktif sayfadaki slot N'in entity_id'sini döndür."""
        # Config sensor'dan current_page'i oku
        config_entity_id = self._get_config_sensor_entity_id()
        current_page = 0
        if config_entity_id:
            state = self.hass.states.get(config_entity_id)
            if state:
                current_page = int(state.attributes.get("current_page", 0))

        pages = get_pages(self._entry)
        if not pages or current_page >= len(pages):
            return None

        buttons = pages[current_page].get(CONF_BUTTONS, [])
        if 0 < self._slot_index <= len(buttons):
            return buttons[self._slot_index - 1].get(CONF_BUTTON_ENTITY) or None
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Config sensor'unun state değişikliklerini dinle (sayfa değişince yeniden track)
        config_entity_id = self._get_config_sensor_entity_id()
        if config_entity_id:
            self._unsub_config_track = async_track_state_change_event(
                self.hass, [config_entity_id], self._handle_config_change
            )
        self._setup_entity_tracking()

    async def async_will_remove_from_hass(self) -> None:
        self._clear_entity_tracking()
        if self._unsub_config_track is not None:
            self._unsub_config_track()
            self._unsub_config_track = None

    def _clear_entity_tracking(self) -> None:
        if self._unsub_entity_track is not None:
            self._unsub_entity_track()
            self._unsub_entity_track = None

    def _setup_entity_tracking(self) -> None:
        self._clear_entity_tracking()
        self._tracked_entity = self._get_current_page_slot_entity()
        if self._tracked_entity:
            self._unsub_entity_track = async_track_state_change_event(
                self.hass, [self._tracked_entity], self._handle_state_change
            )

    @callback
    def _handle_config_change(self, event: Event) -> None:
        """Config sensor değişti (sayfa değişimi vb) → re-track yeni entity'yi."""
        new_entity = self._get_current_page_slot_entity()
        if new_entity != self._tracked_entity:
            self._setup_entity_tracking()
        self.async_write_ha_state()

    @callback
    def _handle_state_change(self, event: Event) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        # Empty slot or stateless domain → off (so ESPHome unchecks the button)
        if not self._tracked_entity:
            return False
        domain = self._tracked_entity.split(".", 1)[0]
        if domain not in ON_STATEFUL_DOMAINS:
            return False
        state = self.hass.states.get(self._tracked_entity)
        if state is None:
            return False
        return state.state.lower() in ("on", "playing", "open", "home")

    # Always available — empty slot reports "off", not "unavailable".
    # Otherwise ESPHome's on_state wouldn't fire when switching to an empty slot
    # and the LVGL button would stay in its previous checked state.
