import bluetooth
import struct
import time
import machine
from machine import TouchPad, Pin
from micropython import const

# ================= CONFIGURATION =================
TOUCH_PIN_NUM = 32
TOUCH_THRESHOLD = 800   # Based on your 700(touch) vs 900(open)
DEBOUNCE_MS = 300       # Prevent double spaces
LED_PIN = 2             # Onboard LED
KEY_HOLD_TIME_MS = 75   # Hold key for 75ms so OS registers it
# =================================================

# --- BLE Constants (Standard HID UUIDs) ---
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)

_HID_SERVICE_UUID = bluetooth.UUID(0x1812)
_HID_INFO_UUID = bluetooth.UUID(0x2A4A)          # <--- NEW: Mandatory for Windows/Mac
_HID_REPORT_MAP_UUID = bluetooth.UUID(0x2A4B)
_HID_CONTROL_POINT_UUID = bluetooth.UUID(0x2A4C)
_HID_REPORT_UUID = bluetooth.UUID(0x2A4D)
_HID_PROTO_MODE_UUID = bluetooth.UUID(0x2A4E)

_ADV_APPEARANCE_KEYBOARD = const(961)

# Standard Keyboard Report Descriptor
_HID_REPORT_DESC = bytes([
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x05, 0x07, 0x19, 0xE0, 0x29, 0xE7, 
    0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x08, 0x81, 0x02, 0x95, 0x01, 
    0x75, 0x08, 0x81, 0x01, 0x95, 0x06, 0x75, 0x08, 0x15, 0x00, 0x25, 0x65, 
    0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00, 0xC0
])

class BLEKeyboard:
    def __init__(self, name="ESP Space"):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        
        # Register HID Service with 5 characteristics (Added HID Info)
        ((self._h_info, self._h_rep_map, self._h_rep, self._h_proto, self._h_ctrl),) = self._ble.gatts_register_services([
            (_HID_SERVICE_UUID, (
                (_HID_INFO_UUID, bluetooth.FLAG_READ),
                (_HID_REPORT_MAP_UUID, bluetooth.FLAG_READ),
                (_HID_REPORT_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY | bluetooth.FLAG_WRITE),
                (_HID_PROTO_MODE_UUID, bluetooth.FLAG_READ | bluetooth.FLAG_WRITE),
                (_HID_CONTROL_POINT_UUID, bluetooth.FLAG_WRITE),
            )),
        ])
        
        # Set initial values
        # 1. HID Info: bcdHID(1.11), bCountryCode(0), Flags(2)
        self._ble.gatts_write(self._h_info, b'\x11\x01\x00\x02')
        # 2. Report Map
        self._ble.gatts_write(self._h_rep_map, _HID_REPORT_DESC)
        # 3. Protocol Mode (Report Protocol = 1)
        self._ble.gatts_write(self._h_proto, b'\x01')
        # 4. Init Report (Empty)
        self._ble.gatts_write(self._h_rep, b'\x00\x00\x00\x00\x00\x00\x00\x00')
        # 5. Control Point (0)
        self._ble.gatts_write(self._h_ctrl, b'\x00')
        
        self._conn_handle = None
        self._payload = advertising_payload(name=name, appearance=_ADV_APPEARANCE_KEYBOARD)
        self._advertise()
        print(f"BLE Ready: Advertising as '{name}'")

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn_handle, _, _ = data
            print("Connected! (Open a text editor now)")
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn_handle = None
            print("Disconnected - Advertising again")
            self._advertise()

    def _advertise(self):
        self._ble.gap_advertise(500000, adv_data=self._payload)

    def send_key(self, key_code):
        if not self._conn_handle:
            return
        
        # 1. Key Down (Modifier=0, Reserved=0, Key=key_code, + 5 zeros)
        self._ble.gatts_notify(self._conn_handle, self._h_rep, struct.pack("8B", 0, 0, key_code, 0, 0, 0, 0, 0))
        
        # 2. WAIT (Essential for OS to see the press)
        time.sleep_ms(KEY_HOLD_TIME_MS)
        
        # 3. Key Up (All zeros)
        self._ble.gatts_notify(self._conn_handle, self._h_rep, struct.pack("8B", 0, 0, 0, 0, 0, 0, 0, 0))

def advertising_payload(limited_disc=False, br_edr=False, name=None, appearance=0):
    payload = bytearray()
    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value

    _append(0x01, struct.pack("B", (0x02 if limited_disc else 0x06) + (0x00 if br_edr else 0x04)))
    if name:
        _append(0x09, name)
    if appearance:
        _append(0x19, struct.pack("<h", appearance))
    _append(0x03, b"\x12\x18") 
    return payload

# --- Main Program ---
def main():
    touch = TouchPad(Pin(TOUCH_PIN_NUM))
    led = Pin(LED_PIN, Pin.OUT)
    led.value(0)
    
    kb = BLEKeyboard()
    KEY_SPACE = 0x2C
    last_press_time = 0
    
    print("Program started. Please Forget/Remove old 'ESP Space' devices first.")

    while True:
        try:
            val = touch.read()
            if val < TOUCH_THRESHOLD:
                now = time.ticks_ms()
                if time.ticks_diff(now, last_press_time) > DEBOUNCE_MS:
                    print(f"Touch ({val}) -> Sending Spacebar")
                    led.value(1)
                    kb.send_key(KEY_SPACE)
                    led.value(0)
                    last_press_time = now
            time.sleep_ms(20)
        except OSError as e:
            print("Error:", e)
            time.sleep(1)

if __name__ == "__main__":
    main()
