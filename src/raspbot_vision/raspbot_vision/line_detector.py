import cv2
import numpy as np


class LineDetector:
    def detect(self, frame, threshold=80, min_area=500, roi_ratio=0.55):
        height, width = frame.shape[:2]
        roi_y_start = int(height * roi_ratio)
        roi = frame[roi_y_start:height, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, binary = cv2.threshold(blur, threshold, 255, cv2.THRESH_BINARY_INV)
        kernel = np.ones((5, 5), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        debug = frame.copy()
        cv2.rectangle(debug, (0, roi_y_start), (width - 1, height - 1), (0, 255, 0), 2)
        if not contours:
            return {'found': False, 'cx': None, 'offset': None, 'debug': debug}
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area < min_area:
            return {'found': False, 'cx': None, 'offset': None, 'debug': debug}
        moments = cv2.moments(largest)
        if moments['m00'] == 0:
            return {'found': False, 'cx': None, 'offset': None, 'debug': debug}
        cx = int(moments['m10'] / moments['m00'])
        cy = int(moments['m01'] / moments['m00']) + roi_y_start
        image_center = width // 2
        offset = cx - image_center
        shifted = largest.copy()
        shifted[:, :, 1] += roi_y_start
        cv2.drawContours(debug, [shifted], -1, (255, 0, 0), 2)
        cv2.circle(debug, (cx, cy), 8, (0, 0, 255), -1)
        cv2.line(debug, (image_center, height), (image_center, roi_y_start), (0, 255, 255), 2)
        cv2.putText(debug, f'offset: {offset}', (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        return {'found': True, 'cx': cx, 'offset': offset, 'debug': debug}
