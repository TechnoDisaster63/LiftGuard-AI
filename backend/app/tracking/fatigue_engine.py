"""
LiftGuard AI - Fatigue Detection Engine
Tracks form degradation over time to detect fatigue and prevent injury.
"""
 
import numpy as np
from collections import deque
import time
 
 
class FatigueDetectionEngine:
    """
    Advanced fatigue detection using multiple signals over time.
    
    Fatigue shows up as:
    1. Increasing spine angle (getting sloppier)
    2. Decreasing movement smoothness (more jerky)
    3. Increasing asymmetry (compensating)
    4. Slower movement (taking longer per lift)
    """
    
    def __init__(self, window_size=100, baseline_lifts=5):
        """
        Initialize fatigue detection engine.
        
        Args:
            window_size: How many frames to keep in history
            baseline_lifts: How many lifts to use for establishing baseline
        """
        self.window_size = window_size
        self.baseline_lifts = baseline_lifts
        
        # Frame-by-frame history
        self.angle_history = deque(maxlen=window_size)
        self.velocity_history = deque(maxlen=window_size)
        self.stability_history = deque(maxlen=window_size)
        self.timestamps = deque(maxlen=window_size)
        
        # Completed lifts for analysis
        self.lift_data = []
        
        # Current lift being tracked
        self.current_lift = {
            'frames': [],
            'start_time': None,
            'max_spine_angle': 0,
            'min_stability': 1.0
        }
        
        # Are we in the middle of a lift?
        self.in_lift = False
        
        # Baseline (established from first N lifts)
        self.baseline = None
        self.baseline_locked = False
        
        # Fatigue metrics
        self.fatigue_score = 100.0  # 100 = fresh, 0 = exhausted
        self.fatigue_trend = 0.0
        self.injury_risk_probability = 0.0
        
        # Alert thresholds
        self.alert_levels = {
            'green': (75, 100),
            'yellow': (50, 75),
            'orange': (25, 50),
            'red': (0, 25)
        }
        
        print("⚡ Fatigue Detection Engine initialized")
    
    def update(self, features_dict, timestamp=None):
        """
        Update fatigue model with new frame data.
        
        Args:
            features_dict: Dictionary of biomechanical features
            timestamp: Current time (defaults to system time)
            
        Returns:
            Dictionary with fatigue status
        """
        if timestamp is None:
            timestamp = time.time()
        
        # Extract key metrics
        spine_angle = features_dict.get('spine_flexion', 0)
        stability = features_dict.get('stability_index', 1)
        
        # Calculate velocity (rate of angle change)
        velocity = 0
        if len(self.angle_history) > 0 and len(self.timestamps) > 0:
            dt = timestamp - self.timestamps[-1]
            if dt > 0:
                velocity = abs(spine_angle - self.angle_history[-1]) / dt
        
        # Store in history
        self.angle_history.append(spine_angle)
        self.velocity_history.append(velocity)
        self.stability_history.append(stability)
        self.timestamps.append(timestamp)
        
        # Detect lift cycles
        self._detect_lift_cycle(spine_angle, timestamp, features_dict)
        
        # Update fatigue model
        if self.baseline_locked:
            self._update_fatigue_score()
        
        return self.get_fatigue_status()
    
    def _detect_lift_cycle(self, spine_angle, timestamp, features):
        """
        Detect when a lift starts and ends.
        """
        LIFT_START_THRESHOLD = 20
        LIFT_END_THRESHOLD = 15
        
        if not self.in_lift and spine_angle > LIFT_START_THRESHOLD:
            # LIFT STARTING
            self.in_lift = True
            self.current_lift = {
                'frames': [features.copy()],
                'start_time': timestamp,
                'max_spine_angle': spine_angle,
                'min_stability': features.get('stability_index', 1)
            }
        
        elif self.in_lift:
            # DURING LIFT
            self.current_lift['frames'].append(features.copy())
            self.current_lift['max_spine_angle'] = max(
                self.current_lift['max_spine_angle'],
                spine_angle
            )
            self.current_lift['min_stability'] = min(
                self.current_lift['min_stability'],
                features.get('stability_index', 1)
            )
            
            # Check if lift ended
            if spine_angle < LIFT_END_THRESHOLD:
                # LIFT COMPLETED
                self.in_lift = False
                self.current_lift['end_time'] = timestamp
                self.current_lift['duration'] = timestamp - self.current_lift['start_time']
                
                # Analyze completed lift
                self._analyze_completed_lift(self.current_lift)
                self.lift_data.append(self.current_lift)
                
                # Lock baseline after N lifts
                if len(self.lift_data) == self.baseline_lifts and not self.baseline_locked:
                    self._calculate_baseline()
    
    def _analyze_completed_lift(self, lift):
        """Extract quality metrics from a completed lift."""
        frames = lift['frames']
        
        if len(frames) < 3:
            return
        
        # Movement smoothness
        angles = [f.get('spine_flexion', 0) for f in frames]
        velocities = np.diff(angles)
        accelerations = np.diff(velocities)
        
        if len(accelerations) > 1:
            jerk = np.mean(np.abs(np.diff(accelerations)))
        else:
            jerk = 0
        
        lift['smoothness'] = 1 / (1 + jerk)
        lift['angle_variance'] = np.var(angles)
        
        # Stability
        stabilities = [f.get('stability_index', 1) for f in frames]
        lift['avg_stability'] = np.mean(stabilities)
        
        # Asymmetry
        asymmetries = [
            f.get('knee_asymmetry', 0) + f.get('hip_asymmetry', 0)
            for f in frames
        ]
        lift['avg_asymmetry'] = np.mean(asymmetries)
    
    def _calculate_baseline(self):
        """Calculate personal baseline from first N lifts."""
        if len(self.lift_data) < self.baseline_lifts:
            return
        
        baseline_lifts = self.lift_data[:self.baseline_lifts]
        
        self.baseline = {
            'max_spine_angle': {
                'mean': np.mean([l['max_spine_angle'] for l in baseline_lifts]),
                'std': np.std([l['max_spine_angle'] for l in baseline_lifts]) + 1
            },
            'duration': {
                'mean': np.mean([l['duration'] for l in baseline_lifts]),
                'std': np.std([l['duration'] for l in baseline_lifts]) + 0.1
            },
            'smoothness': {
                'mean': np.mean([l.get('smoothness', 0.5) for l in baseline_lifts]),
                'std': np.std([l.get('smoothness', 0.5) for l in baseline_lifts]) + 0.1
            },
            'stability': {
                'mean': np.mean([l.get('avg_stability', 0.8) for l in baseline_lifts]),
                'std': np.std([l.get('avg_stability', 0.8) for l in baseline_lifts]) + 0.05
            }
        }
        
        self.baseline_locked = True
        
        print(f"\n✅ Baseline locked from {self.baseline_lifts} lifts")
        print(f"   📐 Avg max spine angle: {self.baseline['max_spine_angle']['mean']:.1f}°")
        print(f"   ⏱️ Avg lift duration: {self.baseline['duration']['mean']:.2f}s")
    
    def _update_fatigue_score(self):
        """Update fatigue score based on deviation from baseline."""
        if not self.baseline or len(self.lift_data) <= self.baseline_lifts:
            return
        
        recent_lifts = self.lift_data[-5:]
        deviations = []
        
        # Spine angle creep
        recent_angles = [l['max_spine_angle'] for l in recent_lifts]
        baseline_angle = self.baseline['max_spine_angle']['mean']
        angle_deviation = (np.mean(recent_angles) - baseline_angle) / self.baseline['max_spine_angle']['std']
        deviations.append(max(0, angle_deviation))
        
        # Smoothness degradation
        recent_smoothness = [l.get('smoothness', 0.5) for l in recent_lifts]
        baseline_smoothness = self.baseline['smoothness']['mean']
        smoothness_deviation = (baseline_smoothness - np.mean(recent_smoothness)) / self.baseline['smoothness']['std']
        deviations.append(max(0, smoothness_deviation))
        
        # Stability degradation
        recent_stability = [l.get('avg_stability', 0.8) for l in recent_lifts]
        baseline_stability = self.baseline['stability']['mean']
        stability_deviation = (baseline_stability - np.mean(recent_stability)) / self.baseline['stability']['std']
        deviations.append(max(0, stability_deviation))
        
        # Duration increase
        recent_durations = [l['duration'] for l in recent_lifts]
        baseline_duration = self.baseline['duration']['mean']
        duration_deviation = (np.mean(recent_durations) - baseline_duration) / self.baseline['duration']['std']
        deviations.append(max(0, duration_deviation))
        
        # Combined fatigue score
        avg_deviation = np.mean(deviations)
        fatigue_delta = avg_deviation * 3
        self.fatigue_score = max(0, self.fatigue_score - fatigue_delta)
        
        # Calculate trend
        if len(self.lift_data) > self.baseline_lifts + 3:
            recent_scores = []
            for i in range(min(5, len(self.lift_data) - self.baseline_lifts)):
                recent_scores.append(100 - (i * fatigue_delta))
            if len(recent_scores) > 1:
                self.fatigue_trend = -np.mean(np.diff(recent_scores))
        
        # Injury probability
        self.injury_risk_probability = 1 / (1 + np.exp(-(50 - self.fatigue_score) / 15))
    
    def get_fatigue_status(self):
        """Get current fatigue status with all metrics."""
        alert_level = 'green'
        for level, (low, high) in self.alert_levels.items():
            if low <= self.fatigue_score < high:
                alert_level = level
                break
        
        if self.fatigue_score < 25:
            alert_level = 'red'
        
        return {
            'fatigue_score': round(self.fatigue_score, 1),
            'fatigue_percentage': round(100 - self.fatigue_score, 1),
            'alert_level': alert_level,
            'injury_probability': round(self.injury_risk_probability * 100, 1),
            'trend': round(self.fatigue_trend, 2),
            'lifts_completed': len(self.lift_data),
            'baseline_locked': self.baseline_locked,
            'recommendation': self._get_recommendation(alert_level)
        }
    
    def _get_recommendation(self, alert_level):
        recommendations = {
            'green': "✅ Form is good. Continue working safely.",
            'yellow': "⚠️ Minor form degradation. Stay mindful.",
            'orange': "🔶 Significant fatigue. Consider a break.",
            'red': "🛑 HIGH FATIGUE. Take a break NOW!"
        }
        return recommendations.get(alert_level, "")
    
    def get_session_report(self):
        """Generate end-of-session report."""
        if len(self.lift_data) == 0:
            return {"error": "No lifts recorded"}
        
        return {
            'total_lifts': len(self.lift_data),
            'session_duration': self.timestamps[-1] - self.timestamps[0] if len(self.timestamps) > 1 else 0,
            'avg_lift_duration': np.mean([l['duration'] for l in self.lift_data if 'duration' in l]),
            'max_spine_angle_reached': max([l['max_spine_angle'] for l in self.lift_data]),
            'form_consistency': 1 - np.std([l['max_spine_angle'] for l in self.lift_data]) / 45,
            'final_fatigue_score': self.fatigue_score,
            'risky_lifts': len([l for l in self.lift_data if l['max_spine_angle'] > 35]),
            'baseline': self.baseline
        }
    
    def reset(self):
        """Reset for new session."""
        self.__init__(self.window_size, self.baseline_lifts)
        print("🔄 Fatigue engine reset")
 
 
# Test if run directly
if __name__ == "__main__":
    print("Testing Fatigue Detection Engine...")
    print("-" * 40)
    
    engine = FatigueDetectionEngine(baseline_lifts=3)
    
    # Simulate 10 lifts
    for i in range(10):
        # Simulate frames within a lift
        for j in range(20):
            features = {
                'spine_flexion': 10 + j * 2 + i * 0.5,
                'stability_index': 0.9 - i * 0.02,
                'hip_hinge_angle': 120 - j - i
            }
            status = engine.update(features)
        
        # Lowering phase
        for j in range(20, 0, -1):
            features = {
                'spine_flexion': 10 + j * 2 + i * 0.5,
                'stability_index': 0.9 - i * 0.02,
                'hip_hinge_angle': 120 - j - i
            }
            status = engine.update(features)
        
        print(f"Lift {i+1}: Fatigue = {status['fatigue_score']:.1f}% | Alert: {status['alert_level']}")
    
    print("-" * 40)
    print("✅ Fatigue Engine Test Complete!")
