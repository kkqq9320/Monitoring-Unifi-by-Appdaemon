[![MIT License](https://img.shields.io/badge/License-MIT-brightgreen?style=for-the-badge&logo=law)](https://opensource.org/licenses/MIT)
[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-0070ba?style=for-the-badge&logo=paypal&logoColor=white)](https://www.paypal.com/paypalme/kkqq9320)
[![Buy Me a Coffee](https://img.shields.io/badge/☕%20Buy%20Me%20a%20Coffee-orange?style=for-the-badge)](https://www.buymeacoffee.com/kkqq9320)


# Monitoring-Unifi-by-Appdaemon

An AppDaemon app for monitoring information related to UniFi routers and access points, available via _[HACS](https://github.com/custom-components/hacs)._

## Confirmed Operating Environment
- **HAOS(VM)**
- **Add-ons**
  - [Appdaemon](https://github.com/hassio-addons/addon-appdaemon)
  - [Mosquitto broker](https://github.com/home-assistant/addons/tree/master/mosquitto)
- **UniFi**
  - Router
    - [Dream Machine Special Edition](https://techspecs.ui.com/unifi/unifi-cloud-gateways/udm-se?subcategory=all-unifi-cloud-gateways)
      <br>_(UDM SE is the only one I've checked, but the data from the other routers doesn't seem to be structurally incorrect, so I think the other routers should work as well.)_
  - Access Point
    - [U6 Extender](https://techspecs.ui.com/unifi/wifi/u6-extender?subcategory=all-wifi)
    - [U6 Mesh](https://techspecs.ui.com/unifi/wifi/u6-mesh?subcategory=all-wifi)
    - [U6 Pro](https://techspecs.ui.com/unifi/wifi/u6-pro?subcategory=all-wifi)
    - [U6+](https://techspecs.ui.com/unifi/wifi/u6-plus?subcategory=all-wifi)
  - Version
    - UniFi OS Version = 4.0.21
    - Network Version = 8.5.6

## Prerequisites
#### UniFi
- You **MUST** create a _local user_. See the [LINK](https://www.home-assistant.io/integrations/unifiprotect/).
- Maybe you need to increase `success.login.limit.count` on UniFi Router. _(Default setting is 5, I increased it to 25)_ SEE [How to](#increase-successloginlimitcount)


#### Homeassistant
- You need an [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) for `MQTT discovery` and a server running the `MQTT broker`.

~~AppDaemon~~
~~MQTT must be defined under plugins in `appdaemon.yaml` since it publishes directly via `MQTT broker`.~~


## How it works
  - ⚠️ _**Only read access**_ is available, and _**NO CONTROL actions**_ can be performed
  - Every 30 seconds, It requests information from the router using the [`UniFi API`](https://ubntwiki.com/products/software/unifi-controller/api)
  - AppDaemon receives and processes the information, then publish it to the `MQTT Broker` through the ~~`AppDaemon MQTT plugin`~~
  - The information sent to the `MQTT Broker` utilizes `MQTT Discovery` to automatically create devices in the `MQTT integration`, categorized by MAC address
    - All AP-related sensors have an entity_id of `sensor.unifi_ap_{device name}_{information type}`, and <br>router-related sensors have an entity_id of `sensor.{device name}_{information type}`.<br>The `{device names}` are all the names you set in the `UniFi web UI`.


  - When the AppDaemon starts, all information is published via MQTT to create the sensor.
  - After the initial publish, publish to the `MQTT Broker` only when the sensor's values (state and attributes) change.
  - If the `Unifi Device` is **unadopted**, or the AppDaemon is turned **off**, the sensor will still have the last value in MQTT.




## Installation
Use [HACS](https://github.com/hacs/integration) or [Download](https://github.com/kkqq9320/Monitoring-Unifi-by-Appdaemon/releases/tag/version) the `monitoring_unifi.py` file from inside the `apps` directory to your local `apps` directory. then add the configuration to enable the `monitoring_unifi` module.

### HACS 
1. To use appdaemon, you must make appdaemon visible in your HACS settings. [CHECK](https://www.hacs.xyz/docs/use/repositories/type/appdaemon/)
2. You can now see appdaemon in the `HACS` tab. go to `HACS` tab
3. Three dots in the upper right > custom repositories > <br>Add `https://github.com/kkqq9320/Monitoring-Unifi-by-Appdaemon` , type is `appdaemon`
4. Search `Monitoring UniFi by Appdaemon` and install
5. If you're having trouble, [CHECK](https://www.hacs.xyz/docs/faq/custom_repositories/)
6. Copy `/homeassistant/appdaemon/apps/Monitoring-Unifi-by-Appdaemon/monitoring_unifi.py`
7. or change appdaemon's `app_dir`. See [appdaemon.yaml](#appdaemonyaml)

### Manual
1. [Download](https://github.com/kkqq9320/Monitoring-Unifi-by-Appdaemon/releases/tag/version) source code.zip and unzip.
2. Copy `Monitoring-Unifi-by-Appdaemon-version/apps/monitoring_unifi.py`

### Next step
1. Now you need to take this and paste it into your `addon_config` directory.
2. Paste file to `/addon_configs/a0d7b954_appdaemon/apps/`
3. `/addon_config` is one level above `/homeassistant` in the file structure.
[CHECK](https://github.com/hassio-addons/addon-appdaemon/releases/tag/v0.15.0)



## Appdamon configuration
### apps.yaml
key | required | type | default | description
-- | -- | -- | -- | --
`module` | Yes | string | monitoring_unifi | The module name of the app.
`class` | Yes | string | MonitoringUnifi | The name of the Class.
`unifi_router_url` | Yes | string | !secret unifi_router_url | Add `https://` before the router's internal IP address <br>(e.g. https://192.168.1.1)
`unifi_local_user` | Yes | string | !secret unifi_local_user | Recommend using `!secret`
`unifi_local_pw` | Yes | string | !secret unifi_local_pw | Recommend using `!secret`
`unifi_router_mac` | Yes | string | !secret unifi_router_mac | Enter the `MAC address` of the Router.<br>Only one `MAC address` can be entered.<br>`'aa:bb:cc:dd:ee:ff'`<br>*Simply copy and paste from the UniFi web UI.*
`unifi_ap_mac` | Yes | list | !secret unifi_ap_mac | Enter the `MAC address` of the Access Points. <br>Multiple `MAC addresses` can be entered.<br>`['11:22:33:44:55:66', 'ab:ac:ad:ae:af:ag']`<br>*Simply copy and paste from the UniFi web UI.*

```yaml
#choose one of the two
---
#When using !secret (Default)
monitoring_unifi:
  module: monitoring_unifi
  class: MonitoringUnifi
  unifi_router_url: !secret unifi_router_url
  unifi_local_user: !secret unifi_local_user
  unifi_local_pw: !secret unifi_local_pw
  unifi_router_mac: !secret unifi_router_mac
  unifi_ap_mac: !secret unifi_ap_mac

---
#direct input
monitoring_unifi:
  module: monitoring_unifi
  class: MonitoringUnifi
  unifi_router_url: 'https://192.168.1.1'
  unifi_local_user: 'mylocalusername'
  unifi_local_pw: 'mylocaluserpw'
  unifi_router_mac: 'aa:bb:cc:dd:ee:ff'
  unifi_ap_mac: ['11:22:33:44:55:66', 'ab:ac:ad:ae:af:ag']
  # whatever you want
  # unifi_ap_mac: 
    # - 11:22:33:44:55:66
    # - ab:ac:ad:ae:af:ag

```
### appdaemon.yaml
```yaml
---
################################################################
# !!!! secrets must be defined. (only when using !secret) !!!! #
################################################################
secrets: /homeassistant/secrets.yaml
appdaemon:
  app_dir: /homeassistant/appdaemon/apps
  latitude: '***REDACTED***'
  longitude: '***REDACTED***'
  elevation: '***REDACTED***'
  time_zone: '***REDACTED***'
  plugins:
    HASS:
      type: hass
      ha_url: '***REDACTED***'
      token: '***REDACTED***'
      namespace: default
    #######################################
    
    #######################################
    # MQTT:
    #   type: mqtt
    #   namespace: mqtt
      # verbose: True
    #  client_host: 192.168.1.100 # your mqtt broker's ip. The IP of homeassistant if installed as an add-on
    # client_port: 1883
    # client_id: "appdaemon"   # Client ID as seen in the MQTT Addon log
    # client_user: !secret mqtt_user
    # client_password: !secret mqtt_pw

http:
  url: http://127.0.0.1:5050
admin:
api:
hadashboard:
```
### secret.yaml
```yaml
unifi_router_url: 'https://192.168.1.1'
unifi_local_user: 'mylocalusername'
unifi_local_pw: 'mylocaluserpw!!'
unifi_router_mac: 'aa:bb:cc:dd:ee:ff'
unifi_ap_mac:
  - 11:22:33:44:55:66
  - ab:ac:ad:ae:af:ag
mqtt_user: "yourmqttusername"
mqtt_pw: "yourmqttpw"
```


## Supproted sensor types
### Common
  - `IP Address`  _(disabled by default)_
  - `Mac Address` _(disabled by default)_
  - `TX`
  - `RX`
### **Router**
  - `Speedtest`
    - `Upload`
    - `Download`
    - `Latency`
    - `Rundate`
      - `CC`
      - `City`
      - `Provider`
### **Access Points**
  - `2.4GHz`, `5GHz`
    - `Channel`
      - `channel width`
      - `channel optimization enabled`
      - `tx power mode`
      - `current tx power` _(only when mode is custom)_
    - `Min RSSI Enabled`
      - `Min RSSI` _(only when min rssi enabled is True)_
    - `Clients` _(number of clients)_
    - `Score`
    - `Uplink [Port / Device]`
      - `uplink type`


## How to
### Increase `success.login.limit.count`
1. Access SSH for change
2. Open the file with vi, and find `success.login.limit.count`
3. Set the value as you wish. The default is 5, but I increased it to 25.
4. A reboot is required for the changes to take effect.
![1](https://github.com/user-attachments/assets/2acfb6f1-76ca-475a-9b01-f83219123bb4)
```code
vi /usr/lib/ulp-go/config.props
```
![1](https://github.com/user-attachments/assets/c5871207-1888-4d65-bf0c-7ad0bc518235)
