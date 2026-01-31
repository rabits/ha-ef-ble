"""Constants for EcoFlow BLE"""

DOMAIN = "ef_ble"
MANUFACTURER = "EcoFlow"

CONF_USER_ID = "user_id"
CONF_UPDATE_PERIOD = "update_period"
CONF_CONNECTION_TIMEOUT = "connection_timeout"
CONF_PACKET_VERSION = "packet_version"
CONF_COLLECT_PACKETS = "collect_packets"
CONF_COLLECT_PACKETS_AMOUNT = "collect_packets_amount"

CONF_LOG_MASKED = "log_masked"
CONF_LOG_PACKETS = "log_packets"
CONF_LOG_ENCRYPTED_PAYLOADS = "log_encrypted_payloads"
CONF_LOG_PAYLOADS = "log_payloads"
CONF_LOG_MESSAGES = "log_messages"
CONF_LOG_CONNECTION = "log_connection"
CONF_LOG_BLEAK = "log_bleak"


DEFAULT_UPDATE_PERIOD = 10
DEFAULT_CONNECTION_TIMEOUT = 20


LINK_WIKI_SUPPORTING_NEW_DEVICES = (
    "https://github.com/rabits/ha-ef-ble/wiki/Requesting-Support-for-New-Devices"
)
