"""Touch Panel Manager integration for Home Assistant."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

# Hangi domain'ler toggle, hangileri turn_on
TOGGLEABLE_DOMAINS = {
    "light", "switch", "input_boolean", "fan", "cover", "media_player", "automation"
}

PANEL_ACTION_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.string,
})

SET_CURRENT_PAGE_SCHEMA = vol.Schema({
    vol.Required("config_entity_id"): cv.string,
    vol.Required("page_index"): vol.Coerce(int),
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bir config entry'yi başlat."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # Servisi sadece bir kez kaydet
    if not hass.services.has_service(DOMAIN, "panel_action"):
        async def _handle_panel_action(call: ServiceCall) -> None:
            """ESPHome cihazından gelen 'bir entity'i çalıştır' isteğini dispatch eder.

            Domain'e göre toggle veya turn_on çağırılır:
              - light, switch, input_boolean, fan, cover, media_player, automation → toggle
              - scene, script, button, vb → turn_on
            """
            entity_id: str = call.data["entity_id"].strip()
            if not entity_id or "." not in entity_id:
                _LOGGER.warning("panel_action: geçersiz entity_id '%s'", entity_id)
                return

            domain = entity_id.split(".", 1)[0]
            action = "toggle" if domain in TOGGLEABLE_DOMAINS else "turn_on"

            _LOGGER.debug("panel_action: %s.%s on %s", "homeassistant", action, entity_id)
            await hass.services.async_call(
                "homeassistant",
                action,
                {"entity_id": entity_id},
                blocking=False,
            )

        hass.services.async_register(
            DOMAIN,
            "panel_action",
            _handle_panel_action,
            schema=PANEL_ACTION_SCHEMA,
        )

    if not hass.services.has_service(DOMAIN, "set_current_page"):
        async def _handle_set_current_page(call: ServiceCall) -> None:
            """ESPHome cihazı sayfa değiştirdiğinde çağırır."""
            config_entity_id: str = call.data["config_entity_id"]
            page_index: int = call.data["page_index"]

            # Tüm entry'lerin config sensor entity'lerini ara, eşleşeni bul
            from homeassistant.helpers import entity_registry as er
            reg = er.async_get(hass)
            target_entry_id = None
            for ent in reg.entities.values():
                if (ent.platform == DOMAIN
                        and ent.entity_id == config_entity_id
                        and ent.unique_id.endswith("_config")):
                    target_entry_id = ent.unique_id.removesuffix("_config")
                    break

            if not target_entry_id:
                _LOGGER.warning("set_current_page: config sensor bulunamadı: %s", config_entity_id)
                return

            # ConfigSensor instance'ını bul ve set_current_page çağır
            from .sensor import TouchPanelConfigSensor
            for state_entity in hass.data["entity_components"]["sensor"].entities:
                if (isinstance(state_entity, TouchPanelConfigSensor)
                        and state_entity._entry.entry_id == target_entry_id):
                    state_entity.set_current_page(page_index)
                    _LOGGER.debug("set_current_page: %s → page %d", config_entity_id, page_index)
                    return

            _LOGGER.warning("set_current_page: ConfigSensor instance bulunamadı")

        hass.services.async_register(
            DOMAIN,
            "set_current_page",
            _handle_set_current_page,
            schema=SET_CURRENT_PAGE_SCHEMA,
        )

    _LOGGER.info("Touch Panel Manager set up: %s", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Config entry'yi kaldır."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        # Son entry de kalkıyorsa servisleri de kaldır
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "panel_action")
            hass.services.async_remove(DOMAIN, "set_current_page")
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Options değişirse entry'yi yeniden yükle."""
    await hass.config_entries.async_reload(entry.entry_id)
