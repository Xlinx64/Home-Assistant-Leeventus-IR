"""Config flow for Leeventus IR."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import infrared
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    CONF_INFRARED_ENTITY_ID,
    CONF_INFRARED_RECEIVER_ENTITY_ID,
    CONF_MODEL,
    DOMAIN,
)
from .models import MODEL_PROFILES, ToiletModel, get_model_profile


class LeeventusIRConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle configuration through the Home Assistant UI."""

    VERSION = 1
    MINOR_VERSION = 2

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        return await self._async_step_config(user_input=user_input)

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Allow changing the model or IR emitter/receiver."""
        return await self._async_step_config(
            user_input=user_input,
            reconfigure_entry=self._get_reconfigure_entry(),
        )

    async def _async_step_config(
        self,
        *,
        user_input: dict[str, Any] | None,
        reconfigure_entry: ConfigEntry | None = None,
    ) -> ConfigFlowResult:
        """Handle the shared setup/reconfigure form."""
        emitter_entity_ids = infrared.async_get_emitters(self.hass)
        receiver_entity_ids = infrared.async_get_receivers(self.hass)
        if not emitter_entity_ids:
            return self.async_abort(reason="no_emitters")

        if user_input is not None:
            data = {
                CONF_MODEL: user_input[CONF_MODEL],
                CONF_INFRARED_ENTITY_ID: user_input[CONF_INFRARED_ENTITY_ID],
            }
            receiver_entity_id = user_input.get(CONF_INFRARED_RECEIVER_ENTITY_ID)
            if receiver_entity_id:
                data[CONF_INFRARED_RECEIVER_ENTITY_ID] = receiver_entity_id

            self._async_abort_entries_match(
                {
                    CONF_MODEL: data[CONF_MODEL],
                    CONF_INFRARED_ENTITY_ID: data[CONF_INFRARED_ENTITY_ID],
                }
            )
            if receiver_entity_id:
                self._async_abort_entries_match(
                    {
                        CONF_MODEL: data[CONF_MODEL],
                        CONF_INFRARED_RECEIVER_ENTITY_ID: receiver_entity_id,
                    }
                )

            title = get_model_profile(data[CONF_MODEL]).display_name
            if reconfigure_entry is None:
                return self.async_create_entry(title=title, data=data)
            return self.async_update_reload_and_abort(
                reconfigure_entry,
                title=title,
                data=data,
            )

        defaults = (
            dict(reconfigure_entry.data)
            if reconfigure_entry is not None
            else {CONF_MODEL: ToiletModel.DIB_J430R}
        )
        schema = vol.Schema(
            {
                _required(CONF_MODEL, defaults): SelectSelector(
                    SelectSelectorConfig(
                        options=[model.value for model in MODEL_PROFILES],
                        translation_key="model",
                    )
                ),
                _required(CONF_INFRARED_ENTITY_ID, defaults): EntitySelector(
                    EntitySelectorConfig(
                        domain=infrared.DOMAIN,
                        include_entities=emitter_entity_ids,
                    )
                ),
                _optional(CONF_INFRARED_RECEIVER_ENTITY_ID, defaults): EntitySelector(
                    EntitySelectorConfig(
                        domain=infrared.DOMAIN,
                        include_entities=receiver_entity_ids,
                    )
                ),
            }
        )
        if reconfigure_entry is not None:
            schema = self.add_suggested_values_to_schema(schema, defaults)

        return self.async_show_form(
            step_id="reconfigure" if reconfigure_entry is not None else "user",
            data_schema=schema,
        )


def _required(key: str, defaults: dict[str, Any]) -> vol.Required:
    """Return a required field marker, with a default when available."""
    if key in defaults:
        return vol.Required(key, default=defaults[key])
    return vol.Required(key)


def _optional(key: str, defaults: dict[str, Any]) -> vol.Optional:
    """Return an optional field marker without injecting a null value."""
    if key in defaults and defaults[key]:
        return vol.Optional(key, default=defaults[key])
    return vol.Optional(key)
