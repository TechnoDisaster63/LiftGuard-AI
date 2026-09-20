"""
LiftGuard AI - Laser Pan-Tilt Keyboard Controller
==================================================
 
CONTROLS:
---------
Arrow Keys:
  ↑ (UP)    = Tilt UP
  ↓ (DOWN)  = Tilt DOWN
  ← (LEFT)  = Pan LEFT
  → (RIGHT) = Pan RIGHT
 
Other Keys:
  W/S       = Tilt UP/DOWN (alternative)
  A/D       = Pan LEFT/RIGHT (alternative)
  
  SPACE     = Toggle Laser ON/OFF
  C         = Center position
  H         = Save as HEAD position
  B         = Save as SPINE/BACK position
  K         = Save as KNEE position
  
  1-9       = Move to preset body parts
  +/=       = Increase step size
  -         = Decrease step size
  
  P         = Print current position
  R         = Reset to center
  T         = Run test sequence
  Q/ESC     = Quit
 
"""
 
import serial
import serial.tools.list_ports
import time
import sys
import os
 
# For keyboard input
try:
    import msvcrt  # Windows
    WINDOWS = True
except ImportError:
    import tty
    import termios
    import select
    WINDOWS = False
 
 
class LaserController:
    """Simple pan-tilt laser controller with keyboard control."""
    
    def __init__(self):
        self.serial = None
        self.connected = False
        
        # Current position
        self.pan = 90
        self.tilt = 90
        self.laser_on = False
        
        # Movement step size
        self.step = 5
        
        # Limits
        self.PAN_MIN = 0
        self.PAN_MAX = 180
        self.TILT_MIN = 0
        self.TILT_MAX = 180
        
        # Saved positions
        self.saved_positions = {
            '1': ('HEAD', 90, 45),
            '2': ('SPINE', 90, 70),
            '3': ('CENTER', 90, 90),
            '4': ('LEFT_SHOULDER', 60, 55),
            '5': ('RIGHT_SHOULDER', 120, 55),
            '6': ('LEFT_KNEE', 55, 120),
            '7': ('RIGHT_KNEE', 125, 120),
            '8': ('LEFT_HIP', 60, 90),
            '9': ('RIGHT_HIP', 120, 90),
        }
    
    def find_arduino(self):
        """Find Arduino port."""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            desc = port.description.lower()
            if 'arduino' in desc or 'ch340' in desc or 'usb' in desc:
                return port.device
        for port in ports:
            if 'COM' in port.device:
                return port.device
        return None
    
    def connect(self):
        """Connect to Arduino."""
        port = self.find_arduino()
        
        if not port:
            print("❌ No Arduino found!")
            print("\nAvailable ports:")
            for p in serial.tools.list_ports.comports():
                print(f"   {p.device} - {p.description}")
            return False
        
        try:
            print(f"🔌 Connecting to {port}...")
            self.serial = serial.Serial(port, 9600, timeout=1)
            time.sleep(2.5)
            self.serial.reset_input_buffer()
            
            # Read startup message
            time.sleep(0.3)
            while self.serial.in_waiting:
                line = self.serial.readline().decode().strip()
                if line:
                    print(f"   Arduino: {line}")
            
            self.connected = True
            print("   ✅ Connected!")
            
            # Center
            self.center()
            return True
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect."""
        if self.serial:
            self.laser_off_cmd()
            time.sleep(0.1)
            self.serial.close()
        self.connected = False
        print("\n🔌 Disconnected")
    
    def send(self, cmd):
        """Send command."""
        if not self.connected:
            return
        try:
            self.serial.write(f"{cmd}\n".encode())
            time.sleep(0.03)
            
            # Read response
            response = ""
            while self.serial.in_waiting:
                response += self.serial.read(self.serial.in_waiting).decode()
            return response.strip()
        except:
            return ""
    
    # ========================================
    # MOVEMENT
    # ========================================
    
    def set_pan(self, angle):
        """Set pan angle."""
        self.pan = max(self.PAN_MIN, min(self.PAN_MAX, angle))
        self.send(f"P{self.pan}")
    
    def set_tilt(self, angle):
        """Set tilt angle."""
        self.tilt = max(self.TILT_MIN, min(self.TILT_MAX, angle))
        self.send(f"T{self.tilt}")
    
    def pan_left(self):
        """Pan left."""
        self.set_pan(self.pan - self.step)
    
    def pan_right(self):
        """Pan right."""
        self.set_pan(self.pan + self.step)
    
    def tilt_up(self):
        """Tilt up."""
        self.set_tilt(self.tilt - self.step)
    
    def tilt_down(self):
        """Tilt down."""
        self.set_tilt(self.tilt + self.step)
    
    def center(self):
        """Center position."""
        self.pan = 90
        self.tilt = 90
        self.send("C")
    
    def move_to(self, pan, tilt):
        """Move to specific position."""
        self.set_pan(pan)
        time.sleep(0.05)
        self.set_tilt(tilt)
    
    # ========================================
    # LASER
    # ========================================
    
    def laser_on_cmd(self):
        """Laser ON."""
        self.laser_on = True
        self.send("L1")
    
    def laser_off_cmd(self):
        """Laser OFF."""
        self.laser_on = False
        self.send("L0")
    
    def toggle_laser(self):
        """Toggle laser."""
        if self.laser_on:
            self.laser_off_cmd()
        else:
            self.laser_on_cmd()
    
    # ========================================
    # DISPLAY
    # ========================================
    
    def clear_screen(self):
        """Clear screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def print_status(self):
        """Print current status."""
        laser_status = "🔴 ON" if self.laser_on else "⚫ OFF"
        
        print(f"\r  PAN: {self.pan:3d}°  |  TILT: {self.tilt:3d}°  |  LASER: {laser_status}  |  STEP: {self.step}°    ", end="", flush=True)
    
    def print_position_visual(self):
        """Print visual position indicator."""
        self.clear_screen()
        
        print("\n" + "="*60)
        print("  🎯 LASER PAN-TILT CONTROLLER")
        print("="*60)
        
        # Status
        laser_status = "🔴 ON " if self.laser_on else "⚫ OFF"
        print(f"\n  PAN: {self.pan:3d}°  |  TILT: {self.tilt:3d}°  |  LASER: {laser_status}  |  STEP: {self.step}°")
        
        # Visual grid
        print("\n  +" + "-"*37 + "+")
        
        for row in range(9):
            tilt_val = row * 22.5  # 0 to 180
            line = "  |"
            
            for col in range(37):
                pan_val = col * 5  # 0 to 180
                
                # Check if current position
                if abs(pan_val - self.pan) < 5 and abs(tilt_val - self.tilt) < 12:
                    if self.laser_on:
                        line += "🔴"
                        col += 1
                    else:
                        line += "✚"
                else:
                    line += " "
            
            # Row label
            if row == 0:
                label = " ↑ HEAD"
            elif row == 4:
                label = " ← CENTER →"
            elif row == 8:
                label = " ↓ FEET"
            else:
                label = ""
            
            print(line + "|" + label)
        
        print("  +" + "-"*37 + "+")
        print("    0°       45°       90°      135°     180°")
        print("   LEFT                                 RIGHT")
        
        # Controls
        print("\n" + "-"*60)
        print("  CONTROLS:")
        print("  ↑↓←→ or WASD = Move    SPACE = Toggle Laser")
        print("  C = Center    +/- = Step Size    P = Print Position")
        print("  1-9 = Presets    T = Test    Q = Quit")
        print("-"*60)
        
        # Presets
        print("\n  PRESETS:")
        for key, (name, p, t) in self.saved_positions.items():
            marker = "◄" if (abs(p - self.pan) < 3 and abs(t - self.tilt) < 3) else " "
            print(f"    [{key}] {name:15} (P:{p:3d}, T:{t:3d}) {marker}")
        
        print("\n" + "="*60)
    
    def print_current_for_code(self):
        """Print current position in code format."""
        print("\n  📋 CURRENT POSITION:")
        print(f"     Pan: {self.pan}°, Tilt: {self.tilt}°")
        print("\n  📝 For Arduino code:")
        print(f"     pan = {self.pan}; tilt = {self.tilt};")
        print("\n  📝 For Python code:")
        print(f"     'CUSTOM': ({self.pan}, {self.tilt}),")
        print()
    
    # ========================================
    # KEYBOARD INPUT
    # ========================================
    
    def get_key(self):
        """Get keyboard input."""
        if WINDOWS:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                
                # Arrow keys (Windows)
                if key == b'\xe0':
                    key2 = msvcrt.getch()
                    if key2 == b'H':
                        return 'UP'
                    elif key2 == b'P':
                        return 'DOWN'
                    elif key2 == b'K':
                        return 'LEFT'
                    elif key2 == b'M':
                        return 'RIGHT'
                
                # Regular keys
                try:
                    return key.decode().upper()
                except:
                    return None
            return None
        else:
            # Linux/Mac
            if select.select([sys.stdin], [], [], 0)[0]:
                key = sys.stdin.read(1)
                
                # Arrow keys
                if key == '\x1b':
                    key2 = sys.stdin.read(2)
                    if key2 == '[A':
                        return 'UP'
                    elif key2 == '[B':
                        return 'DOWN'
                    elif key2 == '[C':
                        return 'RIGHT'
                    elif key2 == '[D':
                        return 'LEFT'
                
                return key.upper()
            return None
    
    def run_test(self):
        """Run test sequence."""
        print("\n  🧪 Running test sequence...")
        
        self.laser_on_cmd()
        time.sleep(0.3)
        
        # Pan test
        print("  Testing pan...")
        for p in [60, 90, 120, 90]:
            self.set_pan(p)
            time.sleep(0.3)
        
        # Tilt test
        print("  Testing tilt...")
        for t in [50, 90, 130, 90]:
            self.set_tilt(t)
            time.sleep(0.3)
        
        # Body parts
        print("  Testing body parts...")
        for key in ['1', '2', '6', '7', '3']:
            name, p, t = self.saved_positions[key]
            print(f"    → {name}")
            self.move_to(p, t)
            time.sleep(0.4)
        
        self.laser_off_cmd()
        self.center()
        print("  ✅ Test complete!")
        time.sleep(1)
    
    # ========================================
    # MAIN LOOP
    # ========================================
    
    def run(self):
        """Main control loop."""
        if not self.connected:
            return
        
        # Set up terminal for Linux/Mac
        if not WINDOWS:
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        
        try:
            self.laser_on_cmd()
            self.print_position_visual()
            
            running = True
            
            while running:
                key = self.get_key()
                
                if key:
                    # Movement
                    if key in ['UP', 'W']:
                        self.tilt_up()
                    elif key in ['DOWN', 'S']:
                        self.tilt_down()
                    elif key in ['LEFT', 'A']:
                        self.pan_left()
                    elif key in ['RIGHT', 'D']:
                        self.pan_right()
                    
                    # Laser
                    elif key == ' ':
                        self.toggle_laser()
                    elif key == 'L':
                        self.toggle_laser()
                    
                    # Center
                    elif key in ['C', 'R']:
                        self.center()
                    
                    # Step size
                    elif key in ['+', '=']:
                        self.step = min(20, self.step + 1)
                    elif key == '-':
                        self.step = max(1, self.step - 1)
                    
                    # Presets (1-9)
                    elif key in self.saved_positions:
                        name, p, t = self.saved_positions[key]
                        self.move_to(p, t)
                    
                    # Print position
                    elif key == 'P':
                        self.print_current_for_code()
                        input("  Press ENTER to continue...")
                    
                    # Test
                    elif key == 'T':
                        self.run_test()
                    
                    # Quit
                    elif key in ['Q', '\x1b', '\x03']:  # Q, ESC, Ctrl+C
                        running = False
                        continue
                    
                    # Update display
                    self.print_position_visual()
                
                time.sleep(0.05)
        
        except KeyboardInterrupt:
            pass
        
        finally:
            # Restore terminal
            if not WINDOWS:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            
            self.laser_off_cmd()
            self.center()
 
 
# ========================================
# MAIN
# ========================================
 
def main():
    print("\n" + "🎮"*20)
    print("\n  LASER PAN-TILT KEYBOARD CONTROLLER")
    print("\n" + "🎮"*20)
    
    controller = LaserController()
    
    if controller.connect():
        print("\n  Starting keyboard control...")
        print("  Use arrow keys or WASD to move")
        print("  Press any key to start...")
        
        # Wait for keypress
        if WINDOWS:
            msvcrt.getch()
        else:
            input()
        
        controller.run()
        controller.disconnect()
    else:
        print("\n  ❌ Failed to connect!")
        print("\n  Troubleshooting:")
        print("  1. Check USB connection")
        print("  2. Upload Arduino code first")
        print("  3. Close Arduino IDE Serial Monitor")
 
 
if __name__ == "__main__":
    main()
