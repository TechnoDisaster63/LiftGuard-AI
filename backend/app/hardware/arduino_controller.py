"""
LIFTGUARD AI - ARDUINO CONTROLLER
Fixed: A=Left, D=Right (Pan direction corrected)
"""
 
import time
import threading

# serial / cv2 / mediapipe are imported lazily inside the methods that use
# them: they are hardware/desktop-only dependencies, and eager module-level
# imports forced every API consumer (and the test suite) to install the
# full CV stack just to import this class.
 
 
class ArduinoController:
    
    # ==========================================
    # DEFAULT POSITIONS
    # ==========================================
    
    DEFAULT_PAN = 108
    DEFAULT_TILT = 139
    
    BODY_POSITIONS = {
        'HEAD':           (108, 60),
        'NOSE':           (108, 55),
        'UPPER_BACK':     (108, 75),
        'SPINE':          (108, 90),
        'CENTER':         (108, 139),
        'LEFT_SHOULDER':  (75, 70),
        'RIGHT_SHOULDER': (141, 70),
        'LEFT_ELBOW':     (60, 95),
        'RIGHT_ELBOW':    (156, 95),
        'LEFT_WRIST':     (50, 115),
        'RIGHT_WRIST':    (166, 115),
        'LEFT_HIP':       (75, 120),
        'RIGHT_HIP':      (141, 120),
        'LEFT_KNEE':      (70, 150),
        'RIGHT_KNEE':     (146, 150),
        'LEFT_ANKLE':     (65, 170),
        'RIGHT_ANKLE':    (151, 170),
    }
    
    def __init__(self):
        # Serial
        self.serial = None
        self.connected = False
        self.port = None
        self.lock = threading.Lock()
        
        # Servo state
        self.current_pan = self.DEFAULT_PAN
        self.current_tilt = self.DEFAULT_TILT
        self.laser_on = False
        
        # For main.py
        self.current_priority = 0
        self.current_body_part = None
        
        # Camera
        self.camera_index = 0
        self.frame_width = 640
        self.frame_height = 480
        self.mirror = True
        
        # Calibration
        self.is_calibrated = False
        self.auto_mode = False
        self.pan_scale = 0
        self.pan_offset = 0
        self.tilt_scale = 0
        self.tilt_offset = 0
        self.calibration_points = {}
        
        # Invert pan direction (FIX)
        self.invert_pan = True  # Set True if A goes right instead of left
        
        # Frame and landmarks from main.py
        self.current_frame = None
        self.current_landmarks = None
        
        # Body part mapping
        self.body_part_to_index = {
            'NOSE': 0, 'HEAD': 0,
            'LEFT_SHOULDER': 11, 'RIGHT_SHOULDER': 12,
            'LEFT_ELBOW': 13, 'RIGHT_ELBOW': 14,
            'LEFT_WRIST': 15, 'RIGHT_WRIST': 16,
            'LEFT_HIP': 23, 'RIGHT_HIP': 24,
            'LEFT_KNEE': 25, 'RIGHT_KNEE': 26,
            'LEFT_ANKLE': 27, 'RIGHT_ANKLE': 28,
            'SPINE': -1, 'CENTER': -1, 'UPPER_BACK': -2,
        }
    
    # ==========================================
    # ARDUINO CONNECTION
    # ==========================================
    
    def find_arduino(self):
        import serial.tools.list_ports

        ports = serial.tools.list_ports.comports()
        for port in ports:
            desc = port.description.lower()
            if 'arduino' in desc or 'ch340' in desc or 'usb serial' in desc:
                return port.device
        for port in ports:
            if 'COM' in port.device:
                return port.device
        return None
    
    def connect(self, port=None):
        import serial

        try:
            if port is None:
                port = self.find_arduino()
            
            if port is None:
                print("Arduino not found!")
                return False
            
            print(f"Connecting to Arduino on {port}...")
            self.serial = serial.Serial(port=port, baudrate=9600, timeout=1)
            time.sleep(2.5)
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
            
            self.connected = True
            self.port = port
            self.center()
            time.sleep(0.3)
            
            print("Arduino connected!")
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        if self.serial and self.connected:
            try:
                self.laser_off()
                self.center()
                time.sleep(0.1)
                self.serial.close()
            except:
                pass
        self.connected = False
        self.serial = None
        print("Arduino disconnected")
    
    def _send(self, command):
        if not self.connected or not self.serial:
            return None
        try:
            with self.lock:
                self.serial.reset_input_buffer()
                self.serial.write(f"{command}\n".encode())
                time.sleep(0.02)
                return True
        except:
            return None
    
    # ==========================================
    # LASER CONTROL
    # ==========================================
    
    def laser_on_cmd(self):
        self.laser_on = True
        self._send("L1")
    
    def laser_off(self):
        self.laser_on = False
        self._send("L0")
    
    def blink(self, times=3):
        self._send(f"B{times}")
    
    def beep(self, duration=100):
        self.blink(3)
    
    # ==========================================
    # SERVO CONTROL
    # ==========================================
    
    def set_pan(self, angle):
        angle = max(0, min(180, int(angle)))
        self.current_pan = angle
        self._send(f"P{angle}")
    
    def set_tilt(self, angle):
        angle = max(0, min(180, int(angle)))
        self.current_tilt = angle
        self._send(f"T{angle}")
    
    def center(self):
        self.current_pan = self.DEFAULT_PAN
        self.current_tilt = self.DEFAULT_TILT
        self._send("C")
    
    def move_to(self, pan, tilt):
        self.set_pan(pan)
        time.sleep(0.01)
        self.set_tilt(tilt)
    
    # ==========================================
    # UPDATE FROM MAIN.PY
    # ==========================================
    
    def update_frame(self, frame, landmarks=None):
        self.current_frame = frame
        self.current_landmarks = landmarks
        if frame is not None:
            self.frame_height, self.frame_width = frame.shape[:2]
    
    # ==========================================
    # CAMERA
    # ==========================================
    
    def list_cameras(self):
        import cv2

        available = []
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    available.append(i)
                cap.release()
        return available
    
    def select_camera(self):
        import cv2

        available = self.list_cameras()
        
        if not available:
            print("No cameras found!")
            return False
        
        if len(available) == 1:
            self.camera_index = available[0]
            return True
        
        print(f"Cameras: {available}")
        print("Y=Select, N=Next, M=Mirror")
        
        for cam in available:
            cap = cv2.VideoCapture(cam)
            start = time.time()
            
            while time.time() - start < 8:
                ret, frame = cap.read()
                if ret:
                    if self.mirror:
                        frame = cv2.flip(frame, 1)
                    
                    cv2.putText(frame, f"Camera {cam}", (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(frame, "Y=Select N=Next M=Mirror", (10, 60),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
                    cv2.imshow("Select Camera", frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('y'):
                    self.camera_index = cam
                    cap.release()
                    cv2.destroyAllWindows()
                    return True
                elif key == ord('n'):
                    break
                elif key == ord('m'):
                    self.mirror = not self.mirror
                elif key == 27:
                    cap.release()
                    cv2.destroyAllWindows()
                    return False
            
            cap.release()
        
        cv2.destroyAllWindows()
        self.camera_index = available[0]
        return True
    
    # ==========================================
    # CALIBRATION (FIXED DIRECTION)
    # ==========================================
    
    def calibrate(self):
        import cv2

        print("\n" + "=" * 50)
        print("   LASER CALIBRATION")
        print("=" * 50)
        print("   Point laser at each RED circle")
        print("   W = Up,  S = Down")
        print("   A = Left,  D = Right")
        print("   Q = Small step,  E = Big step")
        print("   SPACE = Save,  M = Mirror,  ESC = Cancel")
        print("=" * 50)
        
        cap = cv2.VideoCapture(self.camera_index)
        ret, frame = cap.read()
        if ret:
            self.frame_height, self.frame_width = frame.shape[:2]
        
        # 25% margin
        mx = self.frame_width // 4
        my = self.frame_height // 4
        
        corners = [
            ('TOP_LEFT', mx, my),
            ('TOP_RIGHT', self.frame_width - mx, my),
            ('BOTTOM_LEFT', mx, self.frame_height - my),
            ('BOTTOM_RIGHT', self.frame_width - mx, self.frame_height - my),
        ]
        
        self.laser_on_cmd()
        pan, tilt = 90, 90
        self.move_to(pan, tilt)
        step = 5
        idx = 0
        
        while idx < 4:
            ret, frame = cap.read()
            if not ret:
                continue
            
            if self.mirror:
                frame = cv2.flip(frame, 1)
            
            name, tx, ty = corners[idx]
            
            # Draw target
            cv2.circle(frame, (tx, ty), 50, (0, 0, 255), 4)
            cv2.circle(frame, (tx, ty), 25, (0, 255, 255), 3)
            cv2.circle(frame, (tx, ty), 8, (0, 0, 255), -1)
            cv2.line(frame, (tx - 60, ty), (tx + 60, ty), (0, 255, 0), 2)
            cv2.line(frame, (tx, ty - 60), (tx, ty + 60), (0, 255, 0), 2)
            cv2.putText(frame, name, (tx - 50, ty - 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
            # Info bar
            cv2.rectangle(frame, (0, 0), (self.frame_width, 80), (0, 0, 0), -1)
            cv2.putText(frame, f"Point at: {name} ({idx+1}/4)", (10, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(frame, f"Pan={pan} Tilt={tilt} Step={step}", (10, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, "WASD=Move Q=1 E=10 SPACE=Save M=Mirror", (10, 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            # Progress
            for i in range(4):
                color = (0, 255, 0) if i < idx else (100, 100, 100)
                cv2.circle(frame, (self.frame_width - 100 + i * 25, 40), 8, color, -1)
            
            cv2.imshow("Calibration", frame)
            key = cv2.waitKey(1) & 0xFF
            
            # ===== FIXED DIRECTIONS =====
            if key == ord('w'):
                # W = Up = decrease tilt
                tilt = max(0, tilt - step)
                self.move_to(pan, tilt)
            
            elif key == ord('s'):
                # S = Down = increase tilt
                tilt = min(180, tilt + step)
                self.move_to(pan, tilt)
            
            elif key == ord('a'):
                # A = Left
                if self.invert_pan:
                    pan = min(180, pan + step)  # Inverted: increase pan
                else:
                    pan = max(0, pan - step)
                self.move_to(pan, tilt)
            
            elif key == ord('d'):
                # D = Right
                if self.invert_pan:
                    pan = max(0, pan - step)  # Inverted: decrease pan
                else:
                    pan = min(180, pan + step)
                self.move_to(pan, tilt)
            
            elif key == ord('q'):
                step = 1
            elif key == ord('e'):
                step = 10
            elif key == ord('5'):
                step = 5
            elif key == ord('m'):
                self.mirror = not self.mirror
                print(f"   Mirror: {'ON' if self.mirror else 'OFF'}")
            elif key == ord('i'):
                # Toggle invert pan
                self.invert_pan = not self.invert_pan
                print(f"   Invert Pan: {'ON' if self.invert_pan else 'OFF'}")
            elif key == 32:  # SPACE
                self.calibration_points[name] = {
                    'pixel': (tx, ty),
                    'servo': (pan, tilt)
                }
                print(f"   Saved {name}: Pan={pan}, Tilt={tilt}")
                idx += 1
            elif key == 27:  # ESC
                cap.release()
                cv2.destroyAllWindows()
                self.laser_off()
                print("   Cancelled")
                return False
        
        cap.release()
        cv2.destroyAllWindows()
        self.laser_off()
        
        self._calculate_mapping()
        self.is_calibrated = True
        self.auto_mode = True
        
        print("\n   Calibration complete!")
        return True
    
    def _calculate_mapping(self):
        tl = self.calibration_points['TOP_LEFT']
        tr = self.calibration_points['TOP_RIGHT']
        bl = self.calibration_points['BOTTOM_LEFT']
        br = self.calibration_points['BOTTOM_RIGHT']
        
        pan_left = (tl['servo'][0] + bl['servo'][0]) / 2
        pan_right = (tr['servo'][0] + br['servo'][0]) / 2
        tilt_top = (tl['servo'][1] + tr['servo'][1]) / 2
        tilt_bottom = (bl['servo'][1] + br['servo'][1]) / 2
        
        pixel_left = (tl['pixel'][0] + bl['pixel'][0]) / 2
        pixel_right = (tr['pixel'][0] + br['pixel'][0]) / 2
        pixel_top = (tl['pixel'][1] + tr['pixel'][1]) / 2
        pixel_bottom = (bl['pixel'][1] + br['pixel'][1]) / 2
        
        self.pan_scale = (pan_right - pan_left) / (pixel_right - pixel_left)
        self.pan_offset = pan_left - (self.pan_scale * pixel_left)
        self.tilt_scale = (tilt_bottom - tilt_top) / (pixel_bottom - pixel_top)
        self.tilt_offset = tilt_top - (self.tilt_scale * pixel_top)
    
    def pixel_to_servo(self, x, y):
        if not self.is_calibrated:
            return self.DEFAULT_PAN, self.DEFAULT_TILT
        
        pan = (x * self.pan_scale) + self.pan_offset
        tilt = (y * self.tilt_scale) + self.tilt_offset
        
        return int(max(0, min(180, pan))), int(max(0, min(180, tilt)))
    
    # ==========================================
    # GET BODY PART POSITION
    # ==========================================
    
    def get_body_part_position(self, landmarks, body_part):
        body_part = body_part.upper().replace(' ', '_')
        
        if landmarks is None:
            return None, None
        
        if body_part in ['SPINE', 'CENTER']:
            ls = landmarks[11]
            rs = landmarks[12]
            lh = landmarks[23]
            rh = landmarks[24]
            if all(l.visibility > 0.5 for l in [ls, rs, lh, rh]):
                x = (ls.x + rs.x + lh.x + rh.x) / 4
                y = (ls.y + rs.y + lh.y + rh.y) / 4
                return int(x * self.frame_width), int(y * self.frame_height)
        
        elif body_part == 'UPPER_BACK':
            ls = landmarks[11]
            rs = landmarks[12]
            if ls.visibility > 0.5 and rs.visibility > 0.5:
                x = (ls.x + rs.x) / 2
                y = (ls.y + rs.y) / 2
                return int(x * self.frame_width), int(y * self.frame_height)
        
        elif body_part in self.body_part_to_index:
            idx = self.body_part_to_index[body_part]
            if idx >= 0 and idx < len(landmarks):
                lm = landmarks[idx]
                if lm.visibility > 0.5:
                    return int(lm.x * self.frame_width), int(lm.y * self.frame_height)
        
        return None, None
    
    # ==========================================
    # POINT AT BODY PART
    # ==========================================
    
    def point_at_body_part(self, body_part, priority=1):
        if not self.connected:
            return False
        
        body_part = body_part.upper().replace(' ', '_')
        
        # AUTO MODE
        if self.is_calibrated and self.auto_mode and self.current_landmarks is not None:
            x, y = self.get_body_part_position(self.current_landmarks, body_part)
            
            if x is not None:
                pan, tilt = self.pixel_to_servo(x, y)
                self.move_to(pan, tilt)
                self.laser_on_cmd()
                
                self.current_body_part = body_part
                self.current_priority = priority
                return True
        
        # MANUAL MODE
        if body_part in self.BODY_POSITIONS:
            pan, tilt = self.BODY_POSITIONS[body_part]
        else:
            for key in self.BODY_POSITIONS:
                if body_part in key:
                    pan, tilt = self.BODY_POSITIONS[key]
                    body_part = key
                    break
            else:
                pan, tilt = self.DEFAULT_PAN, self.DEFAULT_TILT
                body_part = 'CENTER'
        
        self.move_to(pan, tilt)
        self.laser_on_cmd()
        
        self.current_body_part = body_part
        self.current_priority = priority
        return True
    
    def set_safe(self):
        self.laser_off()
        self.current_priority = 0
        self.current_body_part = None
    
    # ==========================================
    # TEST
    # ==========================================
    
    def test_sequence(self):
        print("\n" + "=" * 50)
        print("   TEST SEQUENCE")
        print("=" * 50)
        
        print("\n1. Laser...")
        self.laser_on_cmd()
        time.sleep(0.5)
        self.laser_off()
        print("   OK")
        
        print("\n2. Blink...")
        self.blink(3)
        time.sleep(0.5)
        print("   OK")
        
        print("\n3. Pan...")
        self.set_pan(self.DEFAULT_PAN - 30)
        time.sleep(0.3)
        self.set_pan(self.DEFAULT_PAN + 30)
        time.sleep(0.3)
        self.set_pan(self.DEFAULT_PAN)
        print("   OK")
        
        print("\n4. Tilt...")
        self.set_tilt(self.DEFAULT_TILT - 40)
        time.sleep(0.3)
        self.set_tilt(self.DEFAULT_TILT + 30)
        time.sleep(0.3)
        self.set_tilt(self.DEFAULT_TILT)
        print("   OK")
        
        print("\n" + "=" * 50)
        print("   TEST COMPLETE!")
        print("=" * 50)
 
 
# ==========================================
# STANDALONE TEST
# ==========================================
 
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("   LIFTGUARD AI - ARDUINO CONTROLLER")
    print("=" * 60)
    
    ctrl = ArduinoController()
    
    if not ctrl.connect():
        exit()
    
    ctrl.test_sequence()
    
    print("\n" + "-" * 60)
    print("   OPTIONS")
    print("-" * 60)
    print("   1 = Manual mode")
    print("   2 = Calibrate")
    print("   3 = Live tracking")
    print("   Q = Quit")
    print("-" * 60)
    
    choice = input("\nChoice: ").strip().upper()
    
    if choice == '1':
        print("\nCommands: L1, L0, P90, T120, C, MHEAD, MSPINE, I=Invert, Q=Quit")
        
        while True:
            try:
                cmd = input("\n>>> ").strip().upper()
                
                if cmd == 'Q':
                    break
                elif cmd == 'L1':
                    ctrl.laser_on_cmd()
                    print("   Laser ON")
                elif cmd == 'L0':
                    ctrl.laser_off()
                    print("   Laser OFF")
                elif cmd.startswith('P') and len(cmd) > 1:
                    ctrl.set_pan(int(cmd[1:]))
                    print(f"   Pan = {cmd[1:]}")
                elif cmd.startswith('T') and len(cmd) > 1:
                    ctrl.set_tilt(int(cmd[1:]))
                    print(f"   Tilt = {cmd[1:]}")
                elif cmd == 'C':
                    ctrl.center()
                    print("   Centered")
                elif cmd == 'I':
                    ctrl.invert_pan = not ctrl.invert_pan
                    print(f"   Invert Pan: {'ON' if ctrl.invert_pan else 'OFF'}")
                elif cmd.startswith('M') and len(cmd) > 1:
                    ctrl.point_at_body_part(cmd[1:], 1)
                    print(f"   Pointing at {cmd[1:]}")
                elif cmd == 'TEST':
                    ctrl.test_sequence()
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"   Error: {e}")
    
    elif choice == '2':
        if ctrl.select_camera():
            ctrl.calibrate()
    
    elif choice == '3':
        if not ctrl.is_calibrated:
            print("\nCalibrating first...")
            if ctrl.select_camera():
                if not ctrl.calibrate():
                    ctrl.disconnect()
                    exit()
        
        print("\n0-9=Body parts, L=Laser, M=Mirror, ESC=Quit")
        
        import cv2
        import mediapipe as mp

        mp_pose = mp.solutions.pose
        mp_draw = mp.solutions.drawing_utils
        pose = mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        
        landmark_names = {
            0: 'NOSE', 11: 'L_SHOULDER', 12: 'R_SHOULDER',
            23: 'L_HIP', 24: 'R_HIP', 25: 'L_KNEE',
            26: 'R_KNEE', 27: 'L_ANKLE', 28: 'R_ANKLE'
        }
        
        key_map = {
            ord('0'): -1, ord('1'): 0, ord('2'): 11, ord('3'): 12,
            ord('4'): 23, ord('5'): 24, ord('6'): 25, ord('7'): 26,
            ord('8'): 27, ord('9'): 28
        }
        
        cap = cv2.VideoCapture(ctrl.camera_index)
        ctrl.laser_on_cmd()
        target_idx = -1
        
        while True:
            ret, frame = cap.read()
            if not ret:
                continue
            
            ctrl.frame_height, ctrl.frame_width = frame.shape[:2]
            
            if ctrl.mirror:
                frame = cv2.flip(frame, 1)
            
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)
            
            if results.pose_landmarks:
                mp_draw.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                
                lm = results.pose_landmarks.landmark
                ctrl.current_landmarks = lm
                
                tx, ty = None, None
                name = ""
                
                if target_idx == -1:
                    pts = [lm[11], lm[12], lm[23], lm[24]]
                    if all(p.visibility > 0.5 for p in pts):
                        tx = int(sum(p.x for p in pts) / 4 * ctrl.frame_width)
                        ty = int(sum(p.y for p in pts) / 4 * ctrl.frame_height)
                        name = "SPINE"
                elif target_idx < len(lm):
                    p = lm[target_idx]
                    if p.visibility > 0.5:
                        tx = int(p.x * ctrl.frame_width)
                        ty = int(p.y * ctrl.frame_height)
                        name = landmark_names.get(target_idx, str(target_idx))
                
                if tx and ty:
                    pan, tilt = ctrl.pixel_to_servo(tx, ty)
                    ctrl.move_to(pan, tilt)
                    
                    cv2.circle(frame, (tx, ty), 25, (0, 0, 255), 3)
                    cv2.circle(frame, (tx, ty), 8, (0, 0, 255), -1)
                    
                    cv2.rectangle(frame, (0, 0), (200, 60), (0, 0, 0), -1)
                    cv2.putText(frame, f"Target: {name}", (10, 25),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                    cv2.putText(frame, f"Pan={pan} Tilt={tilt}", (10, 50),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            cv2.imshow("Tracking", frame)
            key = cv2.waitKey(1) & 0xFF
            
            if key == 27:
                break
            elif key == ord('l'):
                ctrl.laser_on = not ctrl.laser_on
                if ctrl.laser_on:
                    ctrl.laser_on_cmd()
                else:
                    ctrl.laser_off()
            elif key == ord('m'):
                ctrl.mirror = not ctrl.mirror
            elif key == ord('i'):
                ctrl.invert_pan = not ctrl.invert_pan
                print(f"   Invert: {'ON' if ctrl.invert_pan else 'OFF'}")
            elif key in key_map:
                target_idx = key_map[key]
        
        ctrl.laser_off()
        cap.release()
        cv2.destroyAllWindows()
    
    ctrl.disconnect()
