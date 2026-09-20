"""
LiftGuard AI - Exercise Tracker
Handles rep counting, exercise type detection, and session data export.
"""
 
import numpy as np
from collections import deque
import csv
import os
from datetime import datetime
 
 
class ExerciseTracker:
    """
    Tracks exercise type, counts reps, and exports session data.
    
    Features:
    - Automatic exercise type detection (Squat, Deadlift, Bent-Over Row)
    - Rep counting with up/down phase detection
    - CSV export of all session data
    """
    
    def __init__(self):
        print("🏋️ Exercise Tracker initialized")
        
        # ============================================
        # REP COUNTING
        # ============================================
        
        self.rep_count = 0
        self.current_phase = "standing"  # standing, descending, bottom, ascending
        self.phase_history = deque(maxlen=10)
        
        # Thresholds for phase detection
        self.standing_threshold = 20      # Spine angle when standing
        self.bottom_threshold = 40        # Spine angle at bottom of movement
        
        # Track angles for smooth detection
        self.angle_history = deque(maxlen=15)
        self.hip_angle_history = deque(maxlen=15)
        self.knee_angle_history = deque(maxlen=15)
        
        # Rep timing
        self.rep_start_time = None
        self.last_rep_duration = 0
        self.rep_durations = []
        
        # ============================================
        # EXERCISE DETECTION
        # ============================================
        
        self.current_exercise = "Unknown"
        self.exercise_confidence = 0.0
        self.exercise_votes = {
            "Squat": 0,
            "Deadlift": 0,
            "Bent-Over Row": 0,
            "Good Morning": 0,
            "Standing": 0
        }
        self.exercise_locked = False
        self.frames_for_detection = 30  # Frames needed to lock exercise type
        
        # ============================================
        # SESSION DATA FOR CSV EXPORT
        # ============================================
        
        self.session_start_time = datetime.now()
        self.session_data = []  # List of dictionaries for each frame/rep
        self.rep_data = []      # Detailed data for each rep
        
        # Current rep tracking
        self.current_rep_data = {
            'frames': [],
            'max_spine_angle': 0,
            'min_knee_angle': 180,
            'max_hip_flexion': 0
        }
    
    def update(self, features, risk_result=None, fatigue_status=None):
        """
        Update tracker with new frame data.
        
        Args:
            features: Dictionary of biomechanical features
            risk_result: Current risk classification result
            fatigue_status: Current fatigue status
            
        Returns:
            Dictionary with rep count, exercise type, and phase
        """
        # Extract key angles
        spine_angle = features.get('spine_flexion', 0)
        hip_angle = features.get('hip_hinge_angle', 90)
        left_knee = features.get('left_knee_angle', 180)
        right_knee = features.get('right_knee_angle', 180)
        avg_knee_angle = (left_knee + right_knee) / 2
        
        # Store in history
        self.angle_history.append(spine_angle)
        self.hip_angle_history.append(hip_angle)
        self.knee_angle_history.append(avg_knee_angle)
        
        # Detect exercise type (before locking)
        if not self.exercise_locked:
            self._detect_exercise_type(spine_angle, hip_angle, avg_knee_angle)
        
        # Count reps
        self._detect_rep_phase(spine_angle, hip_angle, avg_knee_angle)
        
        # Store frame data for export
        self._store_frame_data(features, risk_result, fatigue_status)
        
        return self.get_status()
    
    def _detect_exercise_type(self, spine_angle, hip_angle, knee_angle):
        """
        Detect which exercise is being performed.
        
        Uses the relationship between spine, hip, and knee angles.
        """
        # Only analyze when in a movement (not standing straight)
        if spine_angle < 15:
            self.exercise_votes["Standing"] += 1
            return
        
        # ============================================
        # SQUAT DETECTION
        # ============================================
        # High knee bend + moderate spine angle + hips back
        # Knees bend significantly (< 120°), spine stays relatively upright
        
        if knee_angle < 130 and spine_angle < 45:
            self.exercise_votes["Squat"] += 2
        
        # ============================================
        # DEADLIFT DETECTION
        # ============================================
        # High hip hinge + high spine angle + knees slightly bent
        # Spine flexes forward, knees have moderate bend
        
        if spine_angle > 35 and knee_angle > 120 and hip_angle < 100:
            self.exercise_votes["Deadlift"] += 2
        
        # ============================================
        # BENT-OVER ROW DETECTION
        # ============================================
        # Sustained forward lean + minimal knee movement
        # Similar to deadlift but held position
        
        if spine_angle > 40 and knee_angle > 140:
            self.exercise_votes["Bent-Over Row"] += 1
        
        # ============================================
        # GOOD MORNING DETECTION
        # ============================================
        # Hip hinge with straight legs
        
        if spine_angle > 45 and knee_angle > 160:
            self.exercise_votes["Good Morning"] += 1
        
        # ============================================
        # DETERMINE WINNER
        # ============================================
        
        total_votes = sum(self.exercise_votes.values())
        
        if total_votes >= self.frames_for_detection:
            # Find exercise with most votes (excluding "Standing")
            exercise_scores = {k: v for k, v in self.exercise_votes.items() if k != "Standing"}
            
            if exercise_scores:
                best_exercise = max(exercise_scores, key=exercise_scores.get)
                best_score = exercise_scores[best_exercise]
                
                # Need at least 30% of votes to be confident
                if best_score > total_votes * 0.25:
                    self.current_exercise = best_exercise
                    self.exercise_confidence = best_score / total_votes
                    self.exercise_locked = True
                    
                    print(f"\n🎯 Exercise Detected: {self.current_exercise}")
                    print(f"   Confidence: {self.exercise_confidence:.0%}")
                    
                    # Adjust thresholds based on exercise
                    self._adjust_thresholds_for_exercise()
    
    def _adjust_thresholds_for_exercise(self):
        """
        Adjust rep detection thresholds based on detected exercise.
        """
        if self.current_exercise == "Squat":
            self.standing_threshold = 15
            self.bottom_threshold = 30
        
        elif self.current_exercise == "Deadlift":
            self.standing_threshold = 15
            self.bottom_threshold = 45
        
        elif self.current_exercise == "Bent-Over Row":
            self.standing_threshold = 35  # Row starts in bent position
            self.bottom_threshold = 50
        
        elif self.current_exercise == "Good Morning":
            self.standing_threshold = 15
            self.bottom_threshold = 50
        
        print(f"   Thresholds adjusted: Stand={self.standing_threshold}°, Bottom={self.bottom_threshold}°")
    
    def _detect_rep_phase(self, spine_angle, hip_angle, knee_angle):
        """
        Detect the current phase of the rep and count completed reps.
        
        Phases: standing → descending → bottom → ascending → standing (1 rep complete)
        """
        # Need some history to detect movement direction
        if len(self.angle_history) < 5:
            return
        
        # Calculate movement direction (positive = bending down, negative = coming up)
        recent_angles = list(self.angle_history)[-5:]
        angle_velocity = recent_angles[-1] - recent_angles[0]
        
        previous_phase = self.current_phase
        
        # ============================================
        # PHASE STATE MACHINE
        # ============================================
        
        if self.current_phase == "standing":
            # Check if starting to descend
            if spine_angle > self.standing_threshold + 5 and angle_velocity > 2:
                self.current_phase = "descending"
                self.rep_start_time = datetime.now()
                
                # Reset current rep tracking
                self.current_rep_data = {
                    'frames': [],
                    'max_spine_angle': spine_angle,
                    'min_knee_angle': knee_angle,
                    'max_hip_flexion': 180 - hip_angle,
                    'start_time': datetime.now()
                }
        
        elif self.current_phase == "descending":
            # Track max values during descent
            self.current_rep_data['max_spine_angle'] = max(
                self.current_rep_data['max_spine_angle'], 
                spine_angle
            )
            self.current_rep_data['min_knee_angle'] = min(
                self.current_rep_data['min_knee_angle'],
                knee_angle
            )
            
            # Check if reached bottom
            if spine_angle > self.bottom_threshold or angle_velocity < -1:
                if spine_angle > self.bottom_threshold * 0.8:  # Close enough to bottom
                    self.current_phase = "bottom"
        
        elif self.current_phase == "bottom":
            # Track max values at bottom
            self.current_rep_data['max_spine_angle'] = max(
                self.current_rep_data['max_spine_angle'],
                spine_angle
            )
            
            # Check if starting to ascend
            if angle_velocity < -3:  # Moving upward
                self.current_phase = "ascending"
        
        elif self.current_phase == "ascending":
            # Check if returned to standing
            if spine_angle < self.standing_threshold and angle_velocity > -1:
                self.current_phase = "standing"
                
                # ============================================
                # REP COMPLETED!
                # ============================================
                
                self.rep_count += 1
                
                # Calculate rep duration
                if self.rep_start_time:
                    self.last_rep_duration = (datetime.now() - self.rep_start_time).total_seconds()
                    self.rep_durations.append(self.last_rep_duration)
                
                # Store rep data
                self.current_rep_data['end_time'] = datetime.now()
                self.current_rep_data['duration'] = self.last_rep_duration
                self.current_rep_data['rep_number'] = self.rep_count
                self.rep_data.append(self.current_rep_data.copy())
                
                print(f"   ✅ Rep {self.rep_count} complete! ({self.last_rep_duration:.1f}s)")
        
        # Store phase change
        if previous_phase != self.current_phase:
            self.phase_history.append(self.current_phase)
    
    def _store_frame_data(self, features, risk_result, fatigue_status):
        """
        Store frame data for CSV export.
        """
        frame_data = {
            'timestamp': datetime.now().isoformat(),
            'rep_count': self.rep_count,
            'phase': self.current_phase,
            'exercise': self.current_exercise,
            
            # Biomechanical features
            'spine_flexion': features.get('spine_flexion', 0),
            'hip_hinge_angle': features.get('hip_hinge_angle', 0),
            'left_knee_angle': features.get('left_knee_angle', 0),
            'right_knee_angle': features.get('right_knee_angle', 0),
            'knee_asymmetry': features.get('knee_asymmetry', 0),
            'stability_index': features.get('stability_index', 0),
            'spinal_load_index': features.get('spinal_load_index', 0),
            
            # Risk data
            'risk_level': risk_result['risk_level'] if risk_result else 0,
            'risk_label': risk_result['risk_label'] if risk_result else 'N/A',
            'risk_confidence': risk_result['confidence'] if risk_result else 0,
            
            # Fatigue data
            'fatigue_score': fatigue_status['fatigue_score'] if fatigue_status else 100,
            'alert_level': fatigue_status['alert_level'] if fatigue_status else 'green',
            'injury_probability': fatigue_status['injury_probability'] if fatigue_status else 0
        }
        
        self.session_data.append(frame_data)
    
    def get_status(self):
        """
        Get current tracking status.
        
        Returns:
            Dictionary with rep count, exercise, phase, etc.
        """
        # Calculate average rep duration
        avg_rep_duration = np.mean(self.rep_durations) if self.rep_durations else 0
        
        return {
            'rep_count': self.rep_count,
            'current_phase': self.current_phase,
            'exercise': self.current_exercise,
            'exercise_confidence': self.exercise_confidence,
            'exercise_locked': self.exercise_locked,
            'last_rep_duration': self.last_rep_duration,
            'avg_rep_duration': avg_rep_duration,
            'phase_display': self._get_phase_display()
        }
    
    def _get_phase_display(self):
        """
        Get a visual representation of current phase.
        """
        phases = {
            'standing': '🧍 Standing',
            'descending': '⬇️ Going Down',
            'bottom': '⏸️ Bottom',
            'ascending': '⬆️ Coming Up'
        }
        return phases.get(self.current_phase, self.current_phase)
    
    def export_to_csv(self, filename=None):
        """
        Export session data to CSV file.
        
        Args:
            filename: Custom filename (optional)
            
        Returns:
            Path to exported file
        """
        if not self.session_data:
            print("⚠️ No data to export")
            return None
        
        # Create exports folder if it doesn't exist
        export_folder = "exports"
        os.makedirs(export_folder, exist_ok=True)
        
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"liftguard_session_{timestamp}.csv"
        
        filepath = os.path.join(export_folder, filename)
        
        # Write CSV
        with open(filepath, 'w', newline='') as csvfile:
            if self.session_data:
                fieldnames = self.session_data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                writer.writerows(self.session_data)
        
        print(f"\n📁 Session data exported to: {filepath}")
        print(f"   Total frames: {len(self.session_data)}")
        print(f"   Total reps: {self.rep_count}")
        
        return filepath
    
    def export_rep_summary(self, filename=None):
        """
        Export rep-by-rep summary to CSV.
        
        Args:
            filename: Custom filename (optional)
            
        Returns:
            Path to exported file
        """
        if not self.rep_data:
            print("⚠️ No rep data to export")
            return None
        
        # Create exports folder
        export_folder = "exports"
        os.makedirs(export_folder, exist_ok=True)
        
        # Generate filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"liftguard_reps_{timestamp}.csv"
        
        filepath = os.path.join(export_folder, filename)
        
        # Prepare rep data for export
        export_data = []
        for rep in self.rep_data:
            export_data.append({
                'rep_number': rep.get('rep_number', 0),
                'duration': rep.get('duration', 0),
                'max_spine_angle': rep.get('max_spine_angle', 0),
                'min_knee_angle': rep.get('min_knee_angle', 0),
                'start_time': rep.get('start_time', '').isoformat() if rep.get('start_time') else '',
                'end_time': rep.get('end_time', '').isoformat() if rep.get('end_time') else ''
            })
        
        # Write CSV
        with open(filepath, 'w', newline='') as csvfile:
            if export_data:
                fieldnames = export_data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                writer.writerows(export_data)
        
        print(f"📁 Rep summary exported to: {filepath}")
        
        return filepath
    
    def get_session_summary(self):
        """
        Get a summary of the session for display.
        
        Returns:
            Dictionary with session summary
        """
        session_duration = (datetime.now() - self.session_start_time).total_seconds()
        
        return {
            'exercise': self.current_exercise,
            'total_reps': self.rep_count,
            'session_duration': session_duration,
            'avg_rep_duration': np.mean(self.rep_durations) if self.rep_durations else 0,
            'fastest_rep': min(self.rep_durations) if self.rep_durations else 0,
            'slowest_rep': max(self.rep_durations) if self.rep_durations else 0,
            'total_frames': len(self.session_data)
        }
    
    def reset(self):
        """
        Reset tracker for a new session.
        """
        self.__init__()
        print("🔄 Exercise tracker reset")
 
 
# Test if run directly
if __name__ == "__main__":
    print("Testing Exercise Tracker...")
    
    tracker = ExerciseTracker()
    
    # Simulate a squat workout
    print("\n--- Simulating Squat Workout ---")
    
    for rep in range(3):
        print(f"\nRep {rep + 1}:")
        
        # Standing
        for i in range(5):
            features = {
                'spine_flexion': 10,
                'hip_hinge_angle': 170,
                'left_knee_angle': 175,
                'right_knee_angle': 175,
                'knee_asymmetry': 0,
                'stability_index': 0.9,
                'spinal_load_index': 0.2
            }
            status = tracker.update(features)
        
        # Going down
        for i in range(10):
            angle = 10 + i * 3
            knee = 175 - i * 5
            features = {
                'spine_flexion': angle,
                'hip_hinge_angle': 170 - i * 5,
                'left_knee_angle': knee,
                'right_knee_angle': knee,
                'knee_asymmetry': 2,
                'stability_index': 0.85,
                'spinal_load_index': 0.3 + i * 0.05
            }
            status = tracker.update(features)
        
        # At bottom
        for i in range(3):
            features = {
                'spine_flexion': 40,
                'hip_hinge_angle': 100,
                'left_knee_angle': 90,
                'right_knee_angle': 90,
                'knee_asymmetry': 3,
                'stability_index': 0.8,
                'spinal_load_index': 0.6
            }
            status = tracker.update(features)
        
        # Coming up
        for i in range(10):
            angle = 40 - i * 3
            knee = 90 + i * 8
            features = {
                'spine_flexion': angle,
                'hip_hinge_angle': 100 + i * 7,
                'left_knee_angle': knee,
                'right_knee_angle': knee,
                'knee_asymmetry': 2,
                'stability_index': 0.85,
                'spinal_load_index': 0.5 - i * 0.03
            }
            status = tracker.update(features)
    
    # Print final status
    print("\n" + "="*40)
    print("Final Status:")
    status = tracker.get_status()
    for k, v in status.items():
        print(f"   {k}: {v}")
    
    # Export to CSV
    print("\n" + "="*40)
    tracker.export_to_csv()
    tracker.export_rep_summary()
    
    # Session summary
    print("\n" + "="*40)
    print("Session Summary:")
    summary = tracker.get_session_summary()
    for k, v in summary.items():
        print(f"   {k}: {v}")
