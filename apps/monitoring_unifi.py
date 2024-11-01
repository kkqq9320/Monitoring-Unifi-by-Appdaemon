import appdaemon.plugins.mqtt.mqttapi as mqtt
import requests
import json
import re
from datetime import datetime
from requests.exceptions import HTTPError, ConnectionError, Timeout
import threading
from typing import Dict, Any, Optional

class MonitoringUnifi(mqtt.Mqtt):
    # Update interval in seconds
    UPDATE_INTERVAL = 30

    def initialize(self) -> None:
        # Configuration from apps.yaml
        self.URL = self.args.get("unifi_router_url")
        self.USER = self.args.get("unifi_local_user") 
        self.PW = self.args.get("unifi_local_pw")
        self.ROUTER_MAC = self.args.get("unifi_router_mac")
        self.AP_MACS = self.args.get("unifi_ap_mac")

        # Validate required configuration
        if not all([self.URL, self.USER, self.PW, self.ROUTER_MAC, self.AP_MACS]):
            self.log("Missing required configuration parameters", level="ERROR")
            return

        # Initialize state tracking
        self.lock = threading.Lock()
        self.last_known_values: Dict[str, Dict[str, Any]] = {}
        self.published_sensors: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.discovery_payloads: Dict[str, Dict[str, Any]] = {}
        self.device_mapping: Dict[str, Dict[str, Any]] = {}
        self.is_fetching = False
        self.session = requests.Session()
        self.session.verify = False

        try:
            self.run_every(self.get_unifi_data, "now", self.UPDATE_INTERVAL)
            self.log(f"Scheduled Unifi data retrieval every {self.UPDATE_INTERVAL} seconds.", level="INFO")
        except Exception as e:
            self.log(f"Initialization error: {str(e)}", level="ERROR")

    def get_unifi_data(self, kwargs: Dict[str, Any]) -> None:
        if not self.is_fetching:
            threading.Thread(target=self.fetch_unifi_data, daemon=True).start()

    def fetch_unifi_data(self) -> None:
        self.is_fetching = True
        session = requests.Session()
        session.verify = False
        try:
            self._login(session)
            self._fetch_devices(session)
            self.run_in(self.process_data_in_main_thread, 0)
        except requests.exceptions.RequestException as e:
            self.log(f"Network error during data fetch: {str(e)}", level="ERROR")
        except Exception as e:
            self.log(f"Data fetch error: {str(e)}", level="ERROR")
        finally:
            session.close()
            self.is_fetching = False


    def _login(self, session: requests.Session) -> None:
        try:
            login_data = {"username": self.USER, "password": self.PW}
            response = session.post(f"{self.URL}/api/auth/login", json=login_data, timeout=10)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            raise TimeoutError("Login request timed out")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Login failed: {str(e)}")

    def _fetch_devices(self, session: requests.Session) -> None:
        try:
            response = session.get(f"{self.URL}/proxy/network/api/s/default/stat/device/", timeout=10)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or 'data' not in data:
                raise ValueError("Invalid data format received from API")
            self.device_mapping = {device['mac']: device for device in data.get('data', [])}
            self.log("Successfully retrieved Unifi device data", level="DEBUG")
        except requests.exceptions.Timeout:
            raise TimeoutError("Device fetch request timed out")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to fetch devices: {str(e)}")
        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Invalid response format: {str(e)}")

    def process_data_in_main_thread(self, kwargs: Dict[str, Any]) -> None:
        self.process_data()

    def process_data(self) -> None:
        try:
            for target_mac in [self.ROUTER_MAC] + self.AP_MACS:
                if device := self.device_mapping.get(target_mac):
                    processor = self.create_router_sensors if target_mac == self.ROUTER_MAC else self.create_ap_sensors
                    processor(device)
                else:
                    self.log(f"Device not found: {target_mac}", level="WARNING")
        except Exception as e:
            self.log(f"Data processing error: {str(e)}", level="ERROR")

    def initialize_device(self, device: Dict[str, Any]) -> tuple:
        name = device.get('name', 'Unknown Device')
        return (
            name,  # friendly_name
            self.make_name_lower(name),  # device_lower_id
            self.make_name_lower(device.get('mac')),  # device_mac_lower
            f"appdaemon/unifi/{self.make_name_lower(name)}"  # base_topic
        )

    def make_name_lower(self, name: Optional[str]) -> str:
        if not name:
            return 'unknown_device'
        name = name.lower()
        name = re.sub(r'\+', '_plus_', name)
        return re.sub(r'[.\s\-:]+', '_', name).strip('_')

    def create_router_sensors(self, device: Dict[str, Any]) -> None:
        friendly_name, device_lower_id, device_mac_lower, base_topic = self.initialize_device(device)
        speedtest = device.get('speedtest-status', {})
        wan = device.get('wan1', {})
        firmware_version = device.get('firmware_version', "Unknown")
        model = device.get('model', "Unknown")

        rundate = speedtest.get('rundate', 'Unknown')
        if isinstance(rundate, int):
            try:
                rundate = datetime.fromtimestamp(rundate).strftime('%Y-%m-%d %H:%M')
            except (ValueError, OSError) as e:
                self.log(f"Error converting timestamp: {str(e)}", level="ERROR")
                rundate = 'Unknown'

        sensors = {
            "IP Address": {"state": device.get('ip'), "category": "diagnostic", "enabled": False},
            "Mac Address": {"state": device.get('mac'), "category": "diagnostic", "enabled": False},
            "Rundate": {
                "state": self.get_valid_value(device_lower_id, 'rundate', rundate),
                "category": "diagnostic",
                "attributes": {
                    "CC": speedtest.get('server', {}).get('cc', 'Unknown'),
                    "City": speedtest.get('server', {}).get('city', 'Unknown'),
                    "Provider": speedtest.get('server', {}).get('provider', 'Unknown')
                }
            },
            "Upload": {
                "state": self.get_valid_value(device_lower_id, 'upload', round(speedtest.get('xput_upload', 0))),
                "unit": "Mbps"
            },
            "Download": {
                "state": self.get_valid_value(device_lower_id, 'download', round(speedtest.get('xput_download', 0))),
                "unit": "Mbps"
            },
            "Latency": {
                "state": self.get_valid_value(device_lower_id, 'latency', speedtest.get('latency', 'Unknown')),
                "category": "diagnostic",
                "unit": "ms"
            },
            "TX": {"state": round(wan.get('tx_bytes-r', 0) / 125000, 3), "unit": "Mbps"},
            "RX": {"state": round(wan.get('rx_bytes-r', 0) / 125000, 3), "unit": "Mbps"}
        }

        self.create_sensor_id_to_publish(device, sensors)

    def get_valid_value(self, device_id: str, metric: str, new_value: Any) -> Any:
        with self.lock:
            if device_id not in self.last_known_values:
                self.last_known_values[device_id] = {}
            
            if new_value not in [0, '1970-01-01 09:00', 'Unknown', None]:
                self.last_known_values[device_id][metric] = new_value
                return new_value
            return self.last_known_values[device_id].get(metric, 'Unknown')

    def create_ap_sensors(self, device: Dict[str, Any]) -> None:
        friendly_name, device_lower_id, device_mac_lower, base_topic = self.initialize_device(device)
        uplink = device.get('uplink', {})
        
        uplink_name = uplink.get('uplink_device_name', 'Unknown')
        uplink_port = uplink.get('uplink_remote_port', 'Unknown')
        uplink_display = f"{uplink_name}, Port {uplink_port}" if uplink_port != 'Unknown' else uplink_name

        sensors = {
            "IP Address": {"state": device.get('ip'), "category": "diagnostic", "enabled": False},
            "MAC Address": {"state": device.get('mac'), "category": "diagnostic", "enabled": False},
            "Uplink": {
                "state": uplink_display,
                "category": "diagnostic",
                "attributes": {"Uplink Type": uplink.get('type', 'Unknown').capitalize()}
            },
            "LED": {
                "state": device.get('led_override'),
                "attributes": {"LED Color": device.get('led_override_color')}
            },
            "TX": {"state": round(uplink.get('tx_bytes-r', 0) / 125000, 3), "unit": "Mbps"},
            "RX": {"state": round(uplink.get('rx_bytes-r', 0) / 125000, 3), "unit": "Mbps"}
        }

        radio_sensors = self.process_radio_data(
            device.get('radio_table', []),
            {
                "Channel": {
                    'state': 'channel',
                    'attributes': {
                        "Channel Width": 'ht',
                        "Channel Optimization Enabled": 'channel_optimization_enabled',
                        "Tx Power Mode": 'tx_power_mode',
                        "Current Tx Power": 'tx_power'
                    }
                },
                "Min RSSI": {
                    'state': 'min_rssi_enabled',
                    'attributes': {"Min RSSI": 'min_rssi'}
                }
            }
        )

        radio_stats = self.process_radio_data(
            device.get('radio_table_stats', []),
            {
                "Score": {'state': 'satisfaction', 'category': 'diagnostic', 'unit': '%'},
                "Clients": {'state': 'num_sta', 'category': 'diagnostic', 'unit': "Clients"}
            }
        )

        sensors.update(radio_sensors)
        sensors.update(radio_stats)
        self.create_sensor_id_to_publish(device, sensors)

    def process_radio_data(self, radio_data: list, sensor_definitions: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        sensors = {}
        for radio in radio_data:
            if radio_type := radio.get('radio'):
                prefix = "2.4ghz" if radio_type == 'ng' else "5ghz" if radio_type == 'na' else None
                if not prefix:
                    continue

                for sensor_name, sensor_info in sensor_definitions.items():
                    sensor_name = f"{prefix} {sensor_name}"
                    state = radio.get(sensor_info['state'], sensor_info.get('default', 'Unknown'))
                    
                    sensor = {'state': state}
                    
                    for key in ['category', 'unit']:
                        if key in sensor_info:
                            sensor[key] = sensor_info[key]

                    if 'attributes' in sensor_info:
                        attributes = {}
                        for attr_name, attr_key in sensor_info['attributes'].items():
                            if (attr_name == 'Current Tx Power' and radio.get('tx_power_mode') == 'custom') or \
                               (attr_name == 'Min RSSI' and radio.get('min_rssi_enabled') is True) or \
                               (attr_name not in ['Current Tx Power', 'Min RSSI']):
                                if value := radio.get(attr_key):
                                    attributes[attr_name] = value
                        
                        if attributes:
                            sensor['attributes'] = attributes
                            
                    sensors[sensor_name] = sensor
        return sensors

    def create_sensor_id_to_publish(self, device: Dict[str, Any], sensors: Dict[str, Dict[str, Any]]) -> None:
        friendly_name, device_lower_id, device_mac_lower, base_topic = self.initialize_device(device)
        for sensor_name, sensor_info in sensors.items():
            try:
                self.publish_sensor(
                    base_topic=base_topic,
                    device_friendly_name=friendly_name,
                    device_lower_id=device_lower_id,
                    device_mac=device_mac_lower,
                    sensor_friendly_name=sensor_name,
                    sensor_lower_id=self.make_name_lower(sensor_name),
                    firmware_version=device.get('version', "Unknown"),
                    model=device.get('model', "Unknown"),
                    **sensor_info
                )
            except Exception as e:
                self.log(f"Error publishing sensor {sensor_name}: {str(e)}", level="ERROR")

    def publish_sensor(self, base_topic: str, device_friendly_name: str, device_lower_id: str, 
                      device_mac: str, sensor_friendly_name: str, sensor_lower_id: str, 
                      firmware_version: str, model: str, state: Any, category: Optional[str] = None, 
                      attributes: Optional[Dict[str, Any]] = None, unit: Optional[str] = None, 
                      enabled: Optional[bool] = None) -> None:
        if state is None:
            return

        try:
            cached_sensor_id = f"{device_mac}_{sensor_lower_id}"
            discovery_topic = f"homeassistant/sensor/{device_lower_id}/{sensor_lower_id}/config"
            state_topic = f"{base_topic}/{sensor_lower_id}/state"
            attributes_topic = f"{base_topic}/{sensor_lower_id}/attributes"

            with self.lock:
                if cached_sensor_id not in self.discovery_payloads:
                    device_info = self.device_mapping.get(device_mac, {})
                    payload = self.generate_payload(
                        state_topic, attributes_topic, category, device_friendly_name,
                        device_lower_id, device_mac, sensor_friendly_name, sensor_lower_id, unit,
                        device_info, firmware_version, model, enabled
                    )
                    self.mqtt_publish(discovery_topic, json.dumps(payload), retain=True)
                    self.discovery_payloads[cached_sensor_id] = payload
                    self.log(f"Published discovery for sensor: {sensor_friendly_name}", level="DEBUG")

                if device_mac not in self.published_sensors:
                    self.published_sensors[device_mac] = {}
                if sensor_lower_id not in self.published_sensors[device_mac]:
                    self.published_sensors[device_mac][sensor_lower_id] = {'state': None, 'attributes': None}

                last_state = self.published_sensors[device_mac][sensor_lower_id]['state']
                last_attributes = self.published_sensors[device_mac][sensor_lower_id]['attributes']

            if state != last_state:
                self.mqtt_publish(state_topic, str(state), retain=True)
                with self.lock:
                    self.published_sensors[device_mac][sensor_lower_id]['state'] = state

            if attributes != last_attributes and attributes:
                self.mqtt_publish(attributes_topic, json.dumps(attributes), retain=True)
                with self.lock:
                    self.published_sensors[device_mac][sensor_lower_id]['attributes'] = attributes

        except Exception as e:
            self.log(f"Error in publish_sensor for {sensor_friendly_name}: {str(e)}", level="ERROR")

    def generate_payload(self, state_topic: str, attributes_topic: str, category: Optional[str],
                        device_friendly_name: str, device_lower_id: str, device_mac: str,
                        sensor_friendly_name: str, sensor_lower_id: str, unit: Optional[str],
                        device_info: Dict[str, Any], firmware_version: str, model: str, enabled: Optional[bool]) -> Dict[str, Any]:
        try:
            object_id_prefix = 'unifi_ap_' if device_mac in [self.make_name_lower(mac) for mac in self.AP_MACS] else ''

            payload = {
                "name": sensor_friendly_name,
                "state_topic": state_topic,
                "unique_id": f"{device_mac}_{sensor_lower_id}",
                "object_id": f"{object_id_prefix}{device_lower_id}_{sensor_lower_id}",
                "device": {
                    "identifiers": [device_mac],
                    "sw_version": firmware_version,
                    "connections": [["mac", device_info.get("mac", device_mac).replace("_", ":")]],
                    "name": device_friendly_name,
                    "model": model,
                    "manufacturer": "AppDaemon"
                }
            }

            if unit:
                payload["unit_of_measurement"] = unit
            if category:
                payload["entity_category"] = category
            if attributes_topic:
                payload["json_attributes_topic"] = attributes_topic
            if enabled is not None:
                payload["enabled_by_default"] = enabled

            return payload

        except Exception as e:
            self.log(f"Error generating payload: {str(e)}", level="ERROR")
            raise
