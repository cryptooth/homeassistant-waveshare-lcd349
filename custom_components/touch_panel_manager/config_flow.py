"""Config flow + Multi-page Options flow for Touch Panel Manager."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BUTTON_ENTITY,
    CONF_BUTTON_LABEL,
    CONF_BUTTONS,
    CONF_INDOOR_TEMP,
    CONF_OUTDOOR_TEMP,
    CONF_PAGE_TITLE,
    CONF_PAGES,
    DEFAULT_NAME,
    DOMAIN,
    MAX_BUTTONS,
    SUPPORTED_BUTTON_DOMAINS,
)


# ─────────────────────────────────────────── Selector helper'ları

def _temperature_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=["sensor"],
            device_class="temperature",
        )
    )


def _button_entity_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=SUPPORTED_BUTTON_DOMAINS,
        )
    )


# ─────────────────────────────────────────── ADD INTEGRATION (sadece isim)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
})


class TouchPanelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """New device flow — just asks the name."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_NAME])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data=user_input,
            )
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return TouchPanelOptionsFlow()


# ─────────────────────────────────────────── OPTIONS FLOW (multi-page menu)

class TouchPanelOptionsFlow(config_entries.OptionsFlow):
    """Menu-driven options flow with add/edit/delete pages."""

    def __init__(self) -> None:
        self._working_options: dict[str, Any] | None = None
        self._editing_page_index: int | None = None

    # ─── Working options init + migration

    def _init_working_options(self) -> None:
        if self._working_options is not None:
            return
        options = dict(self.config_entry.options)

        # Multi-page yoksa legacy "buttons"'ı tek sayfa olarak migrate et
        if CONF_PAGES not in options:
            legacy = options.pop(CONF_BUTTONS, None) or self.config_entry.data.get(CONF_BUTTONS)
            if legacy:
                options[CONF_PAGES] = [{
                    CONF_PAGE_TITLE: "Page 1",
                    CONF_BUTTONS: legacy,
                }]
            else:
                options[CONF_PAGES] = []

        self._working_options = options

    @property
    def _pages(self) -> list[dict]:
        return self._working_options[CONF_PAGES]

    # ─── Page form helpers

    def _page_form_schema(self, page: dict | None) -> vol.Schema:
        page = page or {}
        buttons = page.get(CONF_BUTTONS, [])
        default_title = page.get(CONF_PAGE_TITLE, f"Page {len(self._pages) + 1}")

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_PAGE_TITLE, default=default_title): str,
        }
        for i in range(1, MAX_BUTTONS + 1):
            existing = buttons[i - 1] if i - 1 < len(buttons) else {}
            entity_key = f"slot_{i}_entity"
            label_key = f"slot_{i}_label"

            if existing.get(CONF_BUTTON_ENTITY):
                schema_dict[vol.Optional(entity_key, default=existing[CONF_BUTTON_ENTITY])] = _button_entity_selector()
            else:
                schema_dict[vol.Optional(entity_key)] = _button_entity_selector()

            schema_dict[vol.Optional(label_key, default=existing.get(CONF_BUTTON_LABEL, ""))] = str

        return vol.Schema(schema_dict)

    def _parse_page_form(self, user_input: dict[str, Any]) -> dict:
        title = user_input.get(CONF_PAGE_TITLE, "").strip() or "Untitled"
        buttons: list[dict] = []
        for i in range(1, MAX_BUTTONS + 1):
            entity = user_input.get(f"slot_{i}_entity")
            label = user_input.get(f"slot_{i}_label", "").strip()
            if entity:
                buttons.append({
                    CONF_BUTTON_ENTITY: entity,
                    CONF_BUTTON_LABEL: label or entity,
                })
        return {CONF_PAGE_TITLE: title, CONF_BUTTONS: buttons}

    # ─── Step: init (menu)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        self._init_working_options()

        # Form: user picked an action from selector
        if user_input is not None:
            action = user_input["action"]
            if action == "add":
                return await self.async_step_add_page()
            if action == "sensors":
                return await self.async_step_sensors()
            if action == "finish":
                return await self.async_step_finish()
            if action.startswith("edit_"):
                self._editing_page_index = int(action.removeprefix("edit_"))
                return await self.async_step_edit_page()
            if action.startswith("delete_"):
                self._editing_page_index = int(action.removeprefix("delete_"))
                return await self.async_step_confirm_delete()

        # Build dynamic action list
        options = [{"value": "add", "label": "➕ Add a new page"}]
        for i, p in enumerate(self._pages):
            title = p.get(CONF_PAGE_TITLE, f"Page {i+1}")
            count = len(p.get(CONF_BUTTONS, []))
            options.append({"value": f"edit_{i}", "label": f"✏️ Edit: {title} ({count})"})
        for i, p in enumerate(self._pages):
            title = p.get(CONF_PAGE_TITLE, f"Page {i+1}")
            options.append({"value": f"delete_{i}", "label": f"🗑️ Delete: {title}"})
        options.append({"value": "sensors", "label": "🌡️ Temperature sensors"})
        options.append({"value": "finish", "label": "✅ Save & close"})

        schema = vol.Schema({
            vol.Required("action", default="finish"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode="list")
            )
        })
        return self.async_show_form(step_id="init", data_schema=schema)

    # ─── Step: add_page

    async def async_step_add_page(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            new_page = self._parse_page_form(user_input)
            self._pages.append(new_page)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="add_page",
            data_schema=self._page_form_schema(None),
        )

    # ─── Step: edit_page

    async def async_step_edit_page(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        idx = self._editing_page_index
        if idx is None or idx >= len(self._pages):
            return await self.async_step_init()

        if user_input is not None:
            self._pages[idx] = self._parse_page_form(user_input)
            return await self.async_step_init()

        page = self._pages[idx]
        return self.async_show_form(
            step_id="edit_page",
            data_schema=self._page_form_schema(page),
            description_placeholders={
                "page_title": page.get(CONF_PAGE_TITLE, f"Page {idx + 1}"),
            },
        )

    # ─── Step: confirm_delete

    async def async_step_confirm_delete(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        idx = self._editing_page_index
        if idx is None or idx >= len(self._pages):
            return await self.async_step_init()

        if user_input is not None:
            if user_input.get("confirm"):
                self._pages.pop(idx)
            return await self.async_step_init()

        page = self._pages[idx]
        return self.async_show_form(
            step_id="confirm_delete",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders={
                "page_title": page.get(CONF_PAGE_TITLE, f"Page {idx + 1}"),
            },
        )

    # ─── Step: sensors

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            if user_input.get(CONF_OUTDOOR_TEMP):
                self._working_options[CONF_OUTDOOR_TEMP] = user_input[CONF_OUTDOOR_TEMP]
            else:
                self._working_options.pop(CONF_OUTDOOR_TEMP, None)
            if user_input.get(CONF_INDOOR_TEMP):
                self._working_options[CONF_INDOOR_TEMP] = user_input[CONF_INDOOR_TEMP]
            else:
                self._working_options.pop(CONF_INDOOR_TEMP, None)
            return await self.async_step_init()

        schema_dict: dict[Any, Any] = {}
        if outdoor := self._working_options.get(CONF_OUTDOOR_TEMP):
            schema_dict[vol.Optional(CONF_OUTDOOR_TEMP, default=outdoor)] = _temperature_selector()
        else:
            schema_dict[vol.Optional(CONF_OUTDOOR_TEMP)] = _temperature_selector()
        if indoor := self._working_options.get(CONF_INDOOR_TEMP):
            schema_dict[vol.Optional(CONF_INDOOR_TEMP, default=indoor)] = _temperature_selector()
        else:
            schema_dict[vol.Optional(CONF_INDOOR_TEMP)] = _temperature_selector()

        return self.async_show_form(
            step_id="sensors",
            data_schema=vol.Schema(schema_dict),
        )

    # ─── Step: finish (save)

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        # Remove legacy buttons key (now stored under pages)
        self._working_options.pop(CONF_BUTTONS, None)
        return self.async_create_entry(title="", data=self._working_options)
