# Uses the Person Sensor from Useful Sensors to lock the screen on a laptop when
# no person is detected for a few seconds.
# See https://usfl.ink/ps_dev for the full developer guide.

import bitmaptools
import board
import busio
import digitalio
import displayio
import struct
import time
import usb_hid

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode

# The person sensor has the I2C ID of hex 62, or decimal 98.
PERSON_SENSOR_I2C_ADDRESS = 0x62

# We will be reading raw bytes over I2C, and we'll need to decode them into
# data structures. These strings define the format used for the decoding, and
# are derived from the layouts defined in the developer guide.
PERSON_SENSOR_I2C_HEADER_FORMAT = "BBH"
PERSON_SENSOR_I2C_HEADER_BYTE_COUNT = struct.calcsize(
    PERSON_SENSOR_I2C_HEADER_FORMAT)

PERSON_SENSOR_FACE_FORMAT = "BBBBBBbB"
PERSON_SENSOR_FACE_BYTE_COUNT = struct.calcsize(PERSON_SENSOR_FACE_FORMAT)

PERSON_SENSOR_FACE_MAX = 4
PERSON_SENSOR_RESULT_FORMAT = PERSON_SENSOR_I2C_HEADER_FORMAT + \
    "B" + PERSON_SENSOR_FACE_FORMAT * PERSON_SENSOR_FACE_MAX + "H"
PERSON_SENSOR_RESULT_BYTE_COUNT = struct.calcsize(PERSON_SENSOR_RESULT_FORMAT)

# How long to pause between sensor polls.
PERSON_SENSOR_DELAY = 0.2

# How large a face needs to be to count.
MAIN_FACE_MIN_WIDTH = 32
MAIN_FACE_MIN_HEIGHT = 32

# How long to wait to take the actions. Alter these to adjust the behavior.
MAIN_FACE_TIMEOUT_SECONDS = 5
LOOKIE_LOO_TIMEOUT_SECONDS = 1

# Convert timeout seconds into loop iteration counts.
MAIN_FACE_TIMEOUT_COUNT = int(MAIN_FACE_TIMEOUT_SECONDS / PERSON_SENSOR_DELAY)
LOOKIE_LOO_TIMEOUT_COUNT = int(
    LOOKIE_LOO_TIMEOUT_SECONDS / PERSON_SENSOR_DELAY)

# The Pico doesn't support board.I2C(), so check before calling it. If it isn't
# present then we assume we're on a Pico and call an explicit function.
try:
    i2c = board.I2C()
except:
    i2c = busio.I2C(scl=board.GP5, sda=board.GP4)

# Wait until we can access the bus.
while not i2c.try_lock():
    pass

# Create a keyboard device so we can send the screen lock command.
keyboard = Keyboard(usb_hid.devices)

time_since_main_face_disappeared = 0
time_since_lookie_loo_appeared = 0

# Keep looping and reading the person sensor results.
while True:
    read_data = bytearray(PERSON_SENSOR_RESULT_BYTE_COUNT)
    i2c.readfrom_into(PERSON_SENSOR_I2C_ADDRESS, read_data)

    offset = 0
    (pad1, pad2, payload_bytes) = struct.unpack_from(
        PERSON_SENSOR_I2C_HEADER_FORMAT, read_data, offset)
    offset = offset + PERSON_SENSOR_I2C_HEADER_BYTE_COUNT

    (num_faces) = struct.unpack_from("B", read_data, offset)
    num_faces = int(num_faces[0])
    offset = offset + 1

    faces = []
    for i in range(num_faces):
        (box_confidence, box_left, box_top, box_right, box_bottom, id_confidence, id,
         is_facing) = struct.unpack_from(PERSON_SENSOR_FACE_FORMAT, read_data, offset)
        offset = offset + PERSON_SENSOR_FACE_BYTE_COUNT
        face = {
            "box_confidence": box_confidence,
            "box_left": box_left,
            "box_top": box_top,
            "box_right": box_right,
            "box_bottom": box_bottom,
            "id_confidence": id_confidence,
            "id": id,
            "is_facing": is_facing,
        }
        faces.append(face)
    checksum = struct.unpack_from("H", read_data, offset)

    has_main_face = False
    has_lookie_loo = False
    for face in faces:
        width = face["box_right"] - face["box_left"]
        height = face["box_bottom"] - face["box_top"]
        big_enough_face = (
            width > MAIN_FACE_MIN_WIDTH and height > MAIN_FACE_MIN_HEIGHT)
        if big_enough_face:
            if not has_main_face:
                has_main_face = True
            else:
                if face["is_facing"] and face["box_confidence"] > 90:
                    has_lookie_loo = True

    if has_main_face:
        time_since_main_face_disappeared = 0
    else:
        time_since_main_face_disappeared += 1

    if not has_lookie_loo:
        time_since_lookie_loo_appeared = 0
    else:
        time_since_lookie_loo_appeared += 1

    if time_since_main_face_disappeared == MAIN_FACE_TIMEOUT_COUNT:
        print("Locking!")
        # The key combo for screen lock on Windows is <Windows Key> + L
        keyboard.send(Keycode.GUI, Keycode.L)
        # Uncomment this instead for MacOS.
        # keyboard.send(Keycode.CONTROL, Keycode.GUI, Keycode.ESCAPE)
        # Uncomment this instead for PopOS Linux.
        # keyboard.send(Keycode.GUI, Keycode.ESCAPE)

    if time_since_lookie_loo_appeared == LOOKIE_LOO_TIMEOUT_COUNT:
        keyboard.send(Keycode.GUI, Keycode.M)
        print("Minimizing!")

    time.sleep(PERSON_SENSOR_DELAY)
