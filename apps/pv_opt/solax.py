import time

import pandas as pd

TIMEFORMAT = "%H:%M"
LIMITS = ["start", "end"]
DIRECTIONS = ["charge"]
WRITE_POLL_SLEEP_DURATION = 0.5
BATTERY_VOLTAGE_DEFAULT = 100.0

INVERTER_DEFS = {
    "SOLAX_X1": {
        "MODE_ITEMS": [
            "use_mode",
            "allow_grid_charge",
            "lock_state",
            "backup_grid_charge",
        ],
        "PERIODS": {"charge": 2, "discharge": 0},
        # Default Configuration: Exposed as inverter.config and provides defaults for this inverter for the
        # required config. These config items can be over-written by config specified in the config.yaml
        # file. They are required for the main PV_Opt module and if they cannot be found an ERROR will be
        # raised
        "online": "sensor.{device_name}_battery_capacity",
        "default_config": {
            "id_battery_soc": "sensor.{device_name}_battery_capacity",
            "id_consumption": "sensor.{device_name}_house_load",
            "id_grid_import_today": "sensor.{device_name}_today_s_import_energy",
            "id_grid_export_today": "sensor.{device_name}_today_s_export_energy",
            "supports_hold_soc": True,
            "supports_forced_discharge": True,
            "update_cycle_seconds": 15,
            "battery_minimum_capacity": 10
        },
        # Brand Conguration: Exposed as inverter.brand_config and can be over-written using arguments
        # from the config.yaml file but not rquired outside of this module
        "brand_config": {
            "id_battery_voltage": "sensor.{device_name}_battery_voltage_charge",
            "id_allow_grid_charge": "select.{device_name}_allow_grid_charge",
            "id_battery_charge_max_current": "number.{device_name}_battery_charge_max_current",
            "id_battery_discharge_max_current": "number.{device_name}_battery_discharge_max_current",
            "id_charge_end_time_1": "select.{device_name}_charger_end_time_1",
            "id_charge_start_time_1": "select.{device_name}_charger_start_time_1",
            "id_charge_end_time_2": "select.{device_name}_charger_end_time_2",
            "id_charge_start_time_2": "select.{device_name}_charger_start_time_2",
            "id_max_charge_current": "number.{device_name}_battery_charge_max_current",
            "id_use_mode": "select.{device_name}_charger_use_mode",
            "id_lock_state": "select.{device_name}_lock_state",
            "id_export_duration": "select.{device_name}_export_duration"
        },
    },
}


class InverterController:
    def __init__(self, inverter_type, host) -> None:
        self.host = host
        self.tz = self.host.tz
        if host is not None:
            self.log = host.log
            self.tz = self.host.tz
            self.config = self.host.config

        self.type = inverter_type

        self.brand_config = {}
        for defs, conf in zip(
            [INVERTER_DEFS[self.type][x] for x in ["default_config", "brand_config"]],
            [self.config, self.brand_config],
        ):
            for item in defs:
                if isinstance(defs[item], str):
                    conf[item] = defs[item].replace("{device_name}", self.host.device_name)
                elif isinstance(defs[item], list):
                    conf[item] = [z.replace("{device_name}", self.host.device_name) for z in defs[item]]
                else:
                    conf[item] = defs[item]

        self.log(f"Loading controller for inverter type {self.type}")

    @property
    def timed_mode(self):
        return True

    @property
    def is_online(self):
        entity_id = INVERTER_DEFS[self.type].get("online", (None, None))
        if entity_id is not None:
            entity_id = entity_id.replace("{device_name}", self.host.device_name)
            return self.host.get_state(entity_id) not in ["unknown", "unavailable"]
        else:
            return True

    def enable_timed_mode(self):
        if self.type == "SOLAX_X1":
            pass
        else:
            self._unknown_inverter()

    def control_charge(self, enable, **kwargs):
        if self.type == "SOLAX_X1":
            if enable:
                self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=28800, verbose=True)
                
                power = kwargs.get("power")
                if power is not None:
                    self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=power, verbose=True)
                    self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Enabled Battery Control", verbose=True)

                    voltage = self.host.get_config("battery_voltage")
                    if voltage == 0:
                        voltage = BATTERY_VOLTAGE_DEFAULT
                        self.log(f"Read a battery voltage of zero. Assuming default of {BATTERY_VOLTAGE_DEFAULT}")
                    #current = abs(round(power / voltage, 1))
                    #current = min(current, self.host.get_config("battery_current_limit_amps"))

                    self.log(f"Power {power:0.0f} at {self.host.get_config('battery_voltage')}V")
                else:
                    self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=0, verbose=True)
                    self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=0, verbose=True)
                    self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Disabled", verbose=True)

                    self.log(f"Power is None, disable control")

                target_soc = kwargs.get("target_soc", None)
                if target_soc is not None:
                    self.log(f"Target SOC {target_soc}%")
            else:
                self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=0, verbose=True)
                self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=0, verbose=True)
                self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Disabled", verbose=True)

            self._press_button(entity_id="button.solax_remotecontrol_trigger")
        else:
            self._unknown_inverter()

    def control_discharge(self, enable, **kwargs):
        if self.type == "SOLAX_X1":
            if enable:
                self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=28800, verbose=True)
                
                power = kwargs.get("power")
                if power is not None:
                    self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=power*-1, verbose=True)
                    self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Enabled Battery Control", verbose=True)

                    voltage = self.host.get_config("battery_voltage")
                    if voltage == 0:
                        voltage = BATTERY_VOLTAGE_DEFAULT
                        self.log(f"Read a battery voltage of zero. Assuming default of {BATTERY_VOLTAGE_DEFAULT}")
                    #current = abs(round(power / voltage, 1))
                    #current = min(current, self.host.get_config("battery_current_limit_amps"))

                    self.log(f"Power {power:0.0f} at {self.host.get_config('battery_voltage')}V")
                else:
                    self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=0, verbose=True)
                    self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=0, verbose=True)
                    self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Disabled", verbose=True)

                    self.log(f"Power is None, disable control")

                target_soc = kwargs.get("target_soc", None)
                if target_soc is not None:
                    self.log(f"Target SOC {target_soc}%")
            else:
                self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=0, verbose=True)
                self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=0, verbose=True)
                self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Disabled", verbose=True)

            self._press_button(entity_id="button.solax_remotecontrol_trigger")
        else:
            self._unknown_inverter()

    def _unknown_inverter(self):
        e = f"Unknown inverter type {self.type}"
        self.log(e, level="ERROR")
        self.host.status(e)
        raise Exception(e)

    def hold_soc(self, enable, soc=None):
        if self.type == "SOLAX_X1":
            if enable:
                self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=28800, verbose=True)
                self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=0, verbose=True)
                self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Enabled No Discharge", verbose=True)
            else:
                self._write_to_hass(entity_id="number.solax_remotecontrol_autorepeat_duration", value=0, verbose=True)
                self._write_to_hass(entity_id="number.solax_remotecontrol_active_power", value=0, verbose=True)
                self._select_in_hass(entity_id="select.solax_remotecontrol_power_control", value="Disabled", verbose=True)

            self._press_button(entity_id="button.solax_remotecontrol_trigger")
        else:
            self._unknown_inverter()

    @property
    def status(self):
        status = None
        if self.type == "SOLAX_X1":
            time_now = pd.Timestamp.now(tz=self.tz)
            midnight = time_now.normalize()

            status = {}

            try:
                powerControl = self.host.get_state_retry("select.solax_remotecontrol_power_control")
                power = self.host.get_state_retry("select.solax_remotecontrol_active_power")

                status["charge"] = {
                    "power": power if powerControl == "Enabled Battery Control" and power > 0 else 0,
                    "active": powerControl == "Enabled Battery Control" and power > 0,
                    "start": time_now,
                    "end": time_now
                }
                status["discharge"] = {
                    "power": power * -1 if powerControl == "Enabled Battery Control" and power < 0 else 0,
                    "active": powerControl == "Enabled Battery Control" and power < 0,
                    "start": time_now,
                    "end": time_now
                }
                status["hold_soc"] = {
                    "active": powerControl == "Enabled No Discharge",
                    "soc": 0.0
                }
            except:
                self.log(f"Failed to read inverter status!")

                status["charge"] = {
                    "power": 0.0,
                    "active": False,
                    "start": time_now,
                    "end": time_now
                }
                status["discharge"] = {
                    "power": 0.0,
                    "active": False,
                    "start": time_now,
                    "end": time_now
                }
                status["hold_soc"] = {
                    "active": False,
                    "soc": 0.0
                }

            self.log(f"SolaX status {status}")
        else:
            self._unknown_inverter()

        return status

    def _write_to_hass(self, entity_id, value, **kwargs):
        return self.host.write_and_poll_value(entity_id=entity_id, value=value, **kwargs)

    def _select_in_hass(self, entity_id, value: str, verbose=True):
        changed = False
        written = False

        state = self.host.get_state_retry(entity_id=entity_id)
        diff = state
        changed = state != value

        new_state = None
        if changed:
            try:
                self.host.call_service("select/select_option", entity_id=entity_id, value=value)
                written = False
                retries = 0
                while not written and retries < WRITE_POLL_RETRIES:
                    retries += 1
                    time.sleep(WRITE_POLL_SLEEP)
                    new_state = self.host.get_state_retry(entity_id=entity_id)
                    written = new_state == value

            except:
                written = False

        if verbose:
            str_log = f"Entity: {entity_id:30s} Value: {value}  Old State: {state} "
            str_log += f"New state: {new_state} Diff: {diff}"
            self.log(str_log)

        return (changed, written)
            
    def _press_button(self, entity_id):
        self.host.call_service("button/press", entity_id=entity_id)
        time.sleep(0.5)
        try:
            time_pressed = pd.Timestamp(self.host.get_state_retry(entity_id=entity_id))
            dt = (pd.Timestamp.now(self.tz) - time_pressed).total_seconds()
            if dt < 10:
                self.log(f"Successfully pressed button {entity_id}")
            else:
                self.log(
                    f"Failed to press button {entity_id}. Last pressed at {time_pressed.strftime(TIMEFORMAT)} ({dt:0.2f} seconds ago)"
                )
        except:
            self.log(f"Failed to press button {entity_id}: it appears to never have been pressed.")

