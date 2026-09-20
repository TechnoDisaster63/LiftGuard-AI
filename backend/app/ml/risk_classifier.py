"""
LiftGuard AI - Risk Classifier
Uses the advanced trained ML model for risk assessment.
"""
 
import numpy as np
import os
 
# Try to import advanced classifier
try:
    from ml_trainer import AdvancedRiskClassifier, BiomechanicsDataGenerator, train_and_save_model  # noqa: F401 -- presence in this import is the availability check
    ADVANCED_ML_AVAILABLE = True
except ImportError:
    ADVANCED_ML_AVAILABLE = False
 
 
class LiftRiskClassifier:
    """
    Risk classifier that uses the advanced ML model.
    Falls back to rule-based if advanced model not available.
    """
    
    def __init__(self):
        self.advanced_classifier = None
        self.is_trained = False
        self.use_advanced = False
        
        # Rule-based thresholds (fallback)
        self.thresholds = {
            'spine_safe': 25,
            'spine_low_risk': 35,
            'spine_medium_risk': 50,
            'hip_safe': 140,
            'hip_low_risk': 110,
            'hip_medium_risk': 80,
            'knee_asym_safe': 10,
            'knee_asym_low': 15,
            'knee_asym_medium': 25,
            'stability_safe': 0.7,
            'stability_low': 0.55,
            'stability_medium': 0.4,
            'load_safe': 0.4,
            'load_low': 0.6,
            'load_medium': 0.8
        }
        
        # Feature names for advanced model
        self.feature_names = [
            'spine_flexion', 'hip_hinge_angle', 'knee_asymmetry',
            'stability_index', 'spinal_load_index', 'spine_lateral_tilt',
            'left_knee_angle', 'right_knee_angle', 'knee_valgus_left',
            'knee_valgus_right', 'shoulder_symmetry', 'left_arm_extension',
            'right_arm_extension', 'stance_width', 'movement_smoothness',
            'movement_velocity'
        ]
        
        print("📊 Risk Classifier initialized")
    
    def train_on_synthetic_data(self):
        """Train or load the advanced ML model."""
        model_path = 'models/advanced_classifier.pkl'
        
        # Try to load existing model
        if os.path.exists(model_path):
            print("📂 Loading pre-trained advanced model...")
            try:
                self.advanced_classifier = AdvancedRiskClassifier()
                if self.advanced_classifier.load(model_path):
                    self.use_advanced = True
                    self.is_trained = True
                    print("✅ Advanced ML model loaded!")
                    return self
            except Exception as e:
                print(f"⚠️ Failed to load model: {e}")
        
        # Train new model if ADVANCED_ML_AVAILABLE
        if ADVANCED_ML_AVAILABLE:
            print("🧠 Training new advanced ML model...")
            try:
                self.advanced_classifier = train_and_save_model(
                    n_samples=5000,
                    save_path=model_path
                )
                self.use_advanced = True
                self.is_trained = True
                print("✅ Advanced ML model trained!")
                return self
            except Exception as e:
                print(f"⚠️ Advanced training failed: {e}")
        
        # Fallback to rule-based
        print("📏 Using rule-based classifier (fallback)")
        self.use_advanced = False
        self.is_trained = True
        return self
    
    def extract_biomechanical_features(self, landmarks):
        """Extract biomechanical features from pose landmarks."""
        features = {}
        
        # Calculate body center points
        hip_center = self._midpoint(landmarks[23], landmarks[24])
        shoulder_center = self._midpoint(landmarks[11], landmarks[12])
        knee_center = self._midpoint(landmarks[25], landmarks[26])
        
        # ============================================
        # SPINAL ANALYSIS
        # ============================================
        
        features['spine_flexion'] = self._calculate_angle_from_vertical(
            hip_center, shoulder_center
        )
        
        shoulder_height_diff = abs(landmarks[11][1] - landmarks[12][1])
        shoulder_width = max(abs(landmarks[11][0] - landmarks[12][0]), 0.01)
        features['spine_lateral_tilt'] = (shoulder_height_diff / shoulder_width) * 45
        
        # ============================================
        # HIP MECHANICS
        # ============================================
        
        features['hip_hinge_angle'] = self._calculate_joint_angle(
            shoulder_center, hip_center, knee_center
        )
        
        left_hip = self._calculate_angle(landmarks[11], landmarks[23], landmarks[25])
        right_hip = self._calculate_angle(landmarks[12], landmarks[24], landmarks[26])
        features['hip_asymmetry'] = abs(left_hip - right_hip)
        
        # ============================================
        # KNEE MECHANICS
        # ============================================
        
        features['left_knee_angle'] = self._calculate_joint_angle(
            landmarks[23], landmarks[25], landmarks[27]
        )
        features['right_knee_angle'] = self._calculate_joint_angle(
            landmarks[24], landmarks[26], landmarks[28]
        )
        features['knee_asymmetry'] = abs(
            features['left_knee_angle'] - features['right_knee_angle']
        )
        
        features['knee_valgus_left'] = self._estimate_knee_valgus(
            landmarks[23], landmarks[25], landmarks[27]
        )
        features['knee_valgus_right'] = self._estimate_knee_valgus(
            landmarks[24], landmarks[26], landmarks[28]
        )
        
        # ============================================
        # SHOULDERS & ARMS
        # ============================================
        
        features['shoulder_symmetry'] = abs(
            landmarks[11][1] - landmarks[12][1]
        ) / max(abs(landmarks[11][0] - landmarks[12][0]), 1)
        
        features['left_arm_extension'] = self._distance(landmarks[11], landmarks[15])
        features['right_arm_extension'] = self._distance(landmarks[12], landmarks[16])
        
        # ============================================
        # STABILITY
        # ============================================
        
        features['com_x'], features['com_y'] = self._estimate_center_of_mass(landmarks)
        features['stance_width'] = self._distance(landmarks[27], landmarks[28]) / 500
        features['stability_index'] = self._calculate_stability_index(
            features['com_x'], landmarks[27], landmarks[28]
        )
        
        # ============================================
        # LOAD ESTIMATION
        # ============================================
        
        features['spinal_load_index'] = self._estimate_spinal_load(
            features['spine_flexion'],
            features['left_arm_extension'] + features['right_arm_extension']
        )
        
        # Movement (placeholder - updated by temporal analysis)
        features['movement_smoothness'] = 0.8
        features['movement_velocity'] = 0.3
        
        return features
    
    # ============================================
    # HELPER FUNCTIONS
    # ============================================
    
    def _calculate_angle(self, p1, p2, p3):
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
        return np.degrees(np.arccos(np.clip(cos_angle, -1, 1)))
    
    def _calculate_joint_angle(self, above, joint, below):
        return self._calculate_angle(above, joint, below)
    
    def _calculate_angle_from_vertical(self, bottom, top):
        dx = top[0] - bottom[0]
        dy = top[1] - bottom[1]
        return np.degrees(np.arctan2(abs(dx), abs(dy)))
    
    def _midpoint(self, p1, p2):
        return ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2, (p1[2]+p2[2])/2)
    
    def _distance(self, p1, p2):
        return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2 + (p1[2]-p2[2])**2)
    
    def _estimate_knee_valgus(self, hip, knee, ankle):
        expected_x = (hip[0] + ankle[0]) / 2
        return (knee[0] - expected_x) * 0.5
    
    def _estimate_center_of_mass(self, landmarks):
        hip_center = self._midpoint(landmarks[23], landmarks[24])
        shoulder_center = self._midpoint(landmarks[11], landmarks[12])
        return (hip_center[0]+shoulder_center[0])/2, (hip_center[1]+shoulder_center[1])/2
    
    def _calculate_stability_index(self, com_x, left_ankle, right_ankle):
        base_center = (left_ankle[0] + right_ankle[0]) / 2
        base_width = abs(left_ankle[0] - right_ankle[0])
        if base_width < 0.01:
            return 0.5
        deviation = abs(com_x - base_center)
        return max(0, min(1, 1 - deviation / (base_width/2 + 0.01)))
    
    def _estimate_spinal_load(self, spine_angle, arm_extension):
        angle_rad = np.radians(spine_angle)
        normalized_arm = min(arm_extension / 500, 1)
        return min(np.sin(angle_rad) * (1 + normalized_arm * 0.5), 1)
    
    # ============================================
    # PREDICTION
    # ============================================
    
    def predict_risk(self, features_dict):
        """Predict risk using advanced ML or rule-based fallback."""
        
        # Try advanced ML prediction
        if self.use_advanced and self.advanced_classifier:
            try:
                # Build feature dict for advanced model
                advanced_features = {name: features_dict.get(name, 0) for name in self.feature_names}
                result = self.advanced_classifier.predict(advanced_features)
                
                # Add risk factors
                result['top_risk_factors'] = self._get_risk_factors(features_dict, result['risk_level'])
                return result
                
            except Exception as e:
                print(f"⚠️ Advanced prediction failed, using rules: {e}")
        
        # Rule-based fallback
        return self._rule_based_predict(features_dict)
    
    def _rule_based_predict(self, features_dict):
        """Rule-based prediction (fallback)."""
        spine = features_dict.get('spine_flexion', 0)
        hip = features_dict.get('hip_hinge_angle', 180)
        stability = features_dict.get('stability_index', 1)
        
        # Calculate individual risks
        risks = []
        
        # Spine
        if spine < self.thresholds['spine_safe']:
            risks.append(0)
        elif spine < self.thresholds['spine_low_risk']:
            risks.append(1)
        elif spine < self.thresholds['spine_medium_risk']:
            risks.append(2)
        else:
            risks.append(3)
        
        # Hip
        if hip > self.thresholds['hip_safe']:
            risks.append(0)
        elif hip > self.thresholds['hip_low_risk']:
            risks.append(1)
        elif hip > self.thresholds['hip_medium_risk']:
            risks.append(2)
        else:
            risks.append(3)
        
        # Stability
        if stability > self.thresholds['stability_safe']:
            risks.append(0)
        elif stability > self.thresholds['stability_low']:
            risks.append(1)
        elif stability > self.thresholds['stability_medium']:
            risks.append(2)
        else:
            risks.append(3)
        
        # Final risk
        if spine < 20 and hip > 150 and stability > 0.65:
            risk_level = 0  # Force SAFE for standing
        else:
            risk_level = max(risks)
        
        confidence = 1.0 - min(np.var(risks) / 2, 0.4)
        
        return {
            'risk_level': risk_level,
            'risk_label': ['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK'][risk_level],
            'confidence': confidence,
            'probabilities': [0.25] * 4,
            'top_risk_factors': self._get_risk_factors(features_dict, risk_level)
        }
    
    def _get_risk_factors(self, features, risk_level):
        """Get human-readable risk factors."""
        factors = []
        
        spine = features.get('spine_flexion', 0)
        hip = features.get('hip_hinge_angle', 180)
        stability = features.get('stability_index', 1)
        knee_asym = features.get('knee_asymmetry', 0)
        
        if spine > 35:
            factors.append(f"HIGH spine bend: {spine:.1f}° (keep under 30°)")
        elif spine > 25:
            factors.append(f"Spine flexion: {spine:.1f}° (straighten up)")
        
        if hip < 110:
            factors.append(f"Low hip hinge: {hip:.1f}° (use legs more)")
        
        if stability < 0.6:
            factors.append(f"Unstable: {stability:.2f} (widen stance)")
        
        if knee_asym > 15:
            factors.append(f"Knee imbalance: {knee_asym:.1f}°")
        
        if not factors:
            factors.append("Excellent form! Keep it up!")
        
        return factors
    
    def calibrate_to_person(self, baseline_features_list):
        """Calibrate to a person (placeholder for future)."""
        print(f"✅ Calibrated from {len(baseline_features_list)} samples")
        return self
    
    def save_model(self, path='models/risk_classifier.pkl'):
        """Save model."""
        if self.advanced_classifier:
            self.advanced_classifier.save(path.replace('.pkl', '_advanced.pkl'))
        print("✅ Model saved")
    
    def load_model(self, path='models/risk_classifier.pkl'):
        """Load model."""
        advanced_path = path.replace('.pkl', '_advanced.pkl')
        if os.path.exists(advanced_path) and ADVANCED_ML_AVAILABLE:
            self.advanced_classifier = AdvancedRiskClassifier()
            self.advanced_classifier.load(advanced_path)
            self.use_advanced = True
        self.is_trained = True
        return self
 
 
# Test
if __name__ == "__main__":
    print("Testing Risk Classifier...")
    
    classifier = LiftRiskClassifier()
    classifier.train_on_synthetic_data()
    
    # Test standing
    test = {
        'spine_flexion': 10,
        'hip_hinge_angle': 170,
        'knee_asymmetry': 3,
        'stability_index': 0.9,
        'spinal_load_index': 0.1,
        'spine_lateral_tilt': 2,
        'left_knee_angle': 175,
        'right_knee_angle': 172,
        'knee_valgus_left': 1,
        'knee_valgus_right': -1,
        'shoulder_symmetry': 0.02,
        'left_arm_extension': 120,
        'right_arm_extension': 118,
        'stance_width': 0.2,
        'movement_smoothness': 0.9,
        'movement_velocity': 0.1
    }
    
    result = classifier.predict_risk(test)
    print(f"\nStanding test: {result['risk_label']} ({result['confidence']:.0%})")
    print(f"Factors: {result['top_risk_factors']}")
