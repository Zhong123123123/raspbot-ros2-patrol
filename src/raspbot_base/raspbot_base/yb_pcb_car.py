import math
import smbus


class YB_Pcb_Car:
    def __init__(self, address=0x16, i2c_bus=1):
        self._addr = address
        self._device = smbus.SMBus(i2c_bus)

    def write_u8(self, reg, data):
        self._device.write_byte_data(self._addr, reg, data)

    def write_array(self, reg, data):
        self._device.write_i2c_block_data(self._addr, reg, data)

    def ctrl_car(self, l_dir, l_speed, r_dir, r_speed):
        self.write_array(0x01, [l_dir, l_speed, r_dir, r_speed])

    def control_car(self, speed_left, speed_right):
        left_dir = 1 if speed_left >= 0 else 0
        right_dir = 1 if speed_right >= 0 else 0
        self.ctrl_car(
            left_dir,
            int(min(255, math.fabs(speed_left))),
            right_dir,
            int(min(255, math.fabs(speed_right))),
        )

    def car_stop(self):
        self.write_u8(0x02, 0x00)

    def ctrl_servo(self, servo_id, angle):
        bounded = max(0, min(180, int(angle)))
        self.write_array(0x03, [int(servo_id), bounded])
