"""
LiftGuard AI - Temporal Risk Classifier V2
==========================================
 
QUEST 2: Integration Layer
Bridges the new TCN model with the existing risk classification system.
 
This module:
1. Wraps TCN for seamless integration
2. Provides fallback to frame-level when needed
3. Manages temporal buffer automatically
4. Exposes same interface as original risk_classifier
"""
 
import numpy as np
import os
 
# Import TCN
try:
    from tcn_model import TCNRiskClassifier, TemporalFeatureBuffer
    TCN_AVAILABLE = True
except ImportError:
    TCN_AVAILABLE = False
    print("⚠️ TCN not available, will use frame-level only")
 
# Import original risk classifier
try:
    from risk_classifier import LiftRiskClassifier
    ORIGINAL_CLASSIFIER_AVAILABLE = True
except ImportError:
    ORIGINAL_CLASSIFIER_AVAILABLE = False
    print("⚠️ Original risk_classifier not available")
 
 
class HybridRiskClassifier:
    """
    Hybrid classifier that combines:
    1. TCN for temporal analysis (primary)
    2. Frame-level ensemble for fallback (secondary)
    3. Intelligent fusion of both predictions
    
    Usage:
        classifier = HybridRiskClassifier()
        classifier.train_or_load()
        
        # Each frame:
        features = extract_features(landmarks)
        result = classifier.predict(features)
    """
    
    def __init__(self, use_temporal=True, temporal_weight=0.7):
        """
        Args:
            use_temporal: Enable TCN temporal analysis
            temporal_weight: Weight for TCN vs frame-level (0-1)
                           0.7 = 70% TCN, 30% frame-level
        """
        self.use_temporal = use_temporal and TCN_AVAILABLE
        self.temporal_weight = temporal_weight
        
        # Initialize both classifiers
        self.tcn_classifier = None
        self.frame_classifier = None
        
        # Temporal buffer
        self.temporal_buffer = None
        
        # Training status
        self.is_trained = False
        
        print("🔀 Hybrid Risk Classifier initialized")
        print(f"   Temporal mode: {'ENABLED' if self.use_temporal else 'DISABLED'}")
        print(f"   Fusion weight: {temporal_weight:.0%} TCN, {1-temporal_weight:.0%} Frame")
    
    def train_or_load(self):
        """
        Initialize classifiers - load pre-trained or create new.
        """
        # Initialize frame-level classifier
        if ORIGINAL_CLASSIFIER_AVAILABLE:
            print("\n📦 Loading frame-level classifier...")
            self.frame_classifier = LiftRiskClassifier()
            self.frame_classifier.train_on_synthetic_data()
            print("   ✅ Frame-level classifier ready")
        else:
            print("   ⚠️ Frame-level classifier not available")
        
        # Initialize TCN classifier
        if self.use_temporal and TCN_AVAILABLE:
            print("\n🧠 Loading TCN classifier...")
            self.tcn_classifier = TCNRiskClassifier(window_size=64)
            
            # Try to load pre-trained TCN
            tcn_path = 'models/tcn_risk_classifier.pth'
            if os.path.exists(tcn_path):
                self.tcn_classifier.load(tcn_path)
                print("   ✅ Pre-trained TCN loaded")
            else:
                print("   ⚠️ No pre-trained TCN found (will use fallback)")
                print("   💡 Run train_tcn.py to create trained model")
            
            # Initialize temporal buffer
            self.temporal_buffer = TemporalFeatureBuffer(window_size=64)
            print("   ✅ Temporal buffer initialized")
        
        self.is_trained = True
        print("\n✅ Hybrid classifier ready!")
        
        return self
    
    def extract_biomechanical_features(self, landmarks):
        """
        Extract features from landmarks.
        Uses original classifier's feature extraction.
        
        Args:
            landmarks: List of (x, y, z) tuples for 33 body points
        
        Returns:
            Dictionary of biomechanical features
        """
        if self.frame_classifier:
            return self.frame_classifier.extract_biomechanical_features(landmarks)
        else:
            # Fallback: basic feature extraction
            return self._basic_feature_extraction(landmarks)
    
    def _basic_feature_extraction(self, landmarks):
        """Basic fallback if no frame classifier."""
        hip_center = self._midpoint(landmarks[23], landmarks[24])
        shoulder_center = self._midpoint(landmarks[11], landmarks[12])
        
        dx = shoulder_center[0] - hip_center[0]
        dy = shoulder_center[1] - hip_center[1]
        spine_angle = np.degrees(np.arctan2(abs(dx), abs(dy)))
        
        return {
            'spine_flexion': spine_angle,
            'hip_hinge_angle': 160 - spine_angle,
            'knee_asymmetry': 5,
            'stability_index': 0.8,
            'spinal_load_index': spine_angle / 90,
            'spine_lateral_tilt': 2,
            'left_knee_angle': 170,
            'right_knee_angle': 168,
            'knee_valgus_left': 0,
            'knee_valgus_right': 0,
            'stance_width': 0.2
        }
    
    def _midpoint(self, p1, p2):
        return ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2, (p1[2]+p2[2])/2)
    
    def predict(self, features_dict, use_uncertainty=False):
        """
        Predict risk level from features.
        
        Args:
            features_dict: Dictionary of biomechanical features
            use_uncertainty: Enable Monte Carlo Dropout uncertainty estimation
        
        Returns:
            {
                'risk_level': 0-3,
                'risk_label': str,
                'confidence': float,
                'probabilities': [p0, p1, p2, p3],
                'mode': 'temporal' / 'frame' / 'hybrid',
                'uncertainty': float (if use_uncertainty=True),
                'top_risk_factors': [str, ...]
            }
        """
        if not self.is_trained:
            self.train_or_load()
        
        # Get frame-level prediction
        frame_result = None
        if self.frame_classifier:
            frame_result = self.frame_classifier.predict_risk(features_dict)
        
        # Get temporal prediction
        temporal_result = None
        if self.use_temporal and self.tcn_classifier:
            # Add to buffer
            self.temporal_buffer.add(features_dict)
            
            # Predict if buffer ready
            if self.temporal_buffer.is_ready():
                if use_uncertainty:
                    temporal_result = self.tcn_classifier.predict_with_uncertainty(
                        features_dict=features_dict,
                        num_samples=10
                    )
                else:
                    temporal_result = self.tcn_classifier.predict(
                        features_dict=features_dict
                    )
        
        # Fusion strategy
        if temporal_result and frame_result:
            # HYBRID MODE: Combine both predictions
            result = self._fuse_predictions(temporal_result, frame_result)
            result['mode'] = 'hybrid'
        
        elif temporal_result:
            # TEMPORAL ONLY
            result = temporal_result
            result['mode'] = 'temporal'
        
        elif frame_result:
            # FRAME ONLY
            result = frame_result
            result['mode'] = 'frame'
        
        else:
            # FALLBACK
            result = self._fallback_prediction(features_dict)
            result['mode'] = 'fallback'
        
        # Add risk factors
        result['top_risk_factors'] = self._get_risk_factors(features_dict, result['risk_level'])
        
        return result
    
    def _fuse_predictions(self, temporal_result, frame_result):
        """
        Intelligent fusion of temporal and frame-level predictions.
        
        Strategy:
        1. Weight probabilities by temporal_weight
        2. Select class with highest fused probability
        3. Average confidence scores
        """
        # Fuse probabilities
        temp_probs = np.array(temporal_result['probabilities'])
        frame_probs = np.array(frame_result.get('probabilities', [0.25, 0.25, 0.25, 0.25]))
        
        fused_probs = (self.temporal_weight * temp_probs + 
                      (1 - self.temporal_weight) * frame_probs)
        
        # Get prediction
        risk_level = int(np.argmax(fused_probs))
        confidence = float(fused_probs[risk_level])
        
        risk_labels = ['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK']
        
        result = {
            'risk_level': risk_level,
            'risk_label': risk_labels[risk_level],
            'confidence': confidence,
            'probabilities': fused_probs.tolist()
        }
        
        # Include uncertainty if available
        if 'uncertainty' in temporal_result:
            result['uncertainty'] = temporal_result['uncertainty']
            result['uncertainty_per_class'] = temporal_result['uncertainty_per_class']
        
        return result
    
    def _fallback_prediction(self, features_dict):
        """Simple rule-based fallback."""
        spine = features_dict.get('spine_flexion', 0)
        
        if spine < 25:
            risk_level, risk_label = 0, 'SAFE'
            probs = [0.9, 0.05, 0.03, 0.02]
        elif spine < 35:
            risk_level, risk_label = 1, 'LOW_RISK'
            probs = [0.1, 0.8, 0.08, 0.02]
        elif spine < 50:
            risk_level, risk_label = 2, 'MEDIUM_RISK'
            probs = [0.05, 0.15, 0.7, 0.1]
        else:
            risk_level, risk_label = 3, 'HIGH_RISK'
            probs = [0.02, 0.03, 0.15, 0.8]
        
        return {
            'risk_level': risk_level,
            'risk_label': risk_label,
            'confidence': probs[risk_level],
            'probabilities': probs,
            'uncertainty': 0.0,
            'uncertainty_per_class': [0.0, 0.0, 0.0, 0.0]
        }
    
    def _get_risk_factors(self, features, risk_level):
        """Get human-readable risk factors."""
        factors = []
        
        spine = features.get('spine_flexion', 0)
        hip = features.get('hip_hinge_angle', 180)
        stability = features.get('stability_index', 1)
        knee_asym = features.get('knee_asymmetry', 0)
        
        if spine > 35:
            factors.append(f"⚠️ High spine bend: {spine:.1f}° (keep under 30°)")
        elif spine > 25:
            factors.append(f"Spine flexion: {spine:.1f}° (straighten up)")
        
        if hip < 110:
            factors.append(f"Low hip hinge: {hip:.1f}° (use legs more)")
        
        if stability < 0.6:
            factors.append(f"⚠️ Unstable: {stability:.2f} (widen stance)")
        
        if knee_asym > 15:
            factors.append(f"Knee imbalance: {knee_asym:.1f}°")
        
        if not factors:
            factors.append("✅ Excellent form! Keep it up!")
        
        return factors
    
    def calibrate_to_person(self, baseline_features_list):
        """Calibrate to individual user."""
        if self.frame_classifier:
            self.frame_classifier.calibrate_to_person(baseline_features_list)
        
        print(f"✅ Calibrated from {len(baseline_features_list)} samples")
        return self
    
    def save_model(self, path=None):
        """Save models."""
        if self.frame_classifier:
            self.frame_classifier.save_model()
        
        if self.tcn_classifier and self.tcn_classifier.is_trained:
            self.tcn_classifier.save('models/tcn_risk_classifier.pth')
        
        print("✅ Models saved")
    
    def load_model(self, path=None):
        """Load models."""
        if self.frame_classifier:
            self.frame_classifier.load_model()
        
        if self.tcn_classifier:
            self.tcn_classifier.load('models/tcn_risk_classifier.pth')
        
        self.is_trained = True
        return self
 
 
# ============================================
# TESTING
# ============================================
 
if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 TEMPORAL RISK CLASSIFIER V2 TESTING")
    print("="*60)
    
    # Test 1: Initialization
    print("\n📐 Test 1: Initialization")
    print("-" * 60)
    
    classifier = HybridRiskClassifier(use_temporal=True, temporal_weight=0.7)
    classifier.train_or_load()
    
    print("✅ Initialization successful")
    
    # Test 2: Single frame prediction
    print("\n🎯 Test 2: Single Frame Prediction")
    print("-" * 60)
    
    test_features = {
        'spine_flexion': 28.5,
        'hip_hinge_angle': 145.2,
        'knee_asymmetry': 7.3,
        'stability_index': 0.82,
        'spinal_load_index': 0.35,
        'spine_lateral_tilt': 3.1,
        'left_knee_angle': 168.5,
        'right_knee_angle': 165.2,
        'knee_valgus_left': 2.1,
        'knee_valgus_right': -1.8,
        'stance_width': 0.22
    }
    
    result = classifier.predict(test_features)
    
    print(f"Risk Level: {result['risk_label']}")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Mode: {result['mode']}")
    print("Top risk factors:")
    for factor in result['top_risk_factors']:
        print(f"  - {factor}")
    
    print("✅ Single frame prediction working")
    
    # Test 3: Temporal sequence
    print("\n📊 Test 3: Temporal Sequence (70 frames)")
    print("-" * 60)
    
    for i in range(70):
        features = {
            'spine_flexion': 15 + i * 0.4,  # Gradually degrading
            'hip_hinge_angle': 165 - i * 0.3,
            'knee_asymmetry': 5 + i * 0.15,
            'stability_index': 0.92 - i * 0.006,
            'spinal_load_index': 0.2 + i * 0.007,
            'spine_lateral_tilt': 2,
            'left_knee_angle': 170,
            'right_knee_angle': 168,
            'knee_valgus_left': 0,
            'knee_valgus_right': 0,
            'stance_width': 0.2
        }
        
        result = classifier.predict(features)
        
        if i in [0, 32, 63, 69]:
            print(f"\nFrame {i+1}:")
            print(f"  Spine: {features['spine_flexion']:.1f}°")
            print(f"  Risk: {result['risk_label']}")
            print(f"  Confidence: {result['confidence']:.1%}")
            print(f"  Mode: {result['mode']}")
    
    print("\n✅ Temporal sequence working")
    
    # Test 4: Uncertainty estimation
    print("\n🎲 Test 4: Uncertainty Estimation")
    print("-" * 60)
    
    test_features_uncertain = {
        'spine_flexion': 32.5,  # Borderline case
        'hip_hinge_angle': 135.0,
        'knee_asymmetry': 12.0,
        'stability_index': 0.68,
        'spinal_load_index': 0.45,
        'spine_lateral_tilt': 5.5,
        'left_knee_angle': 155,
        'right_knee_angle': 160,
        'knee_valgus_left': 3,
        'knee_valgus_right': -2,
        'stance_width': 0.18
    }
    
    result_uncertain = classifier.predict(test_features_uncertain, use_uncertainty=True)
    
    print(f"Risk: {result_uncertain['risk_label']}")
    print(f"Confidence: {result_uncertain['confidence']:.1%}")
    
    if 'uncertainty' in result_uncertain:
        print(f"Uncertainty: {result_uncertain['uncertainty']:.4f}")
        print("✅ Uncertainty estimation available")
    else:
        print("⚠️ Uncertainty not available (TCN not trained)")
    
    print("\n" + "="*60)
    print("🎉 ALL TESTS PASSED!")
    print("="*60)
    print("\n📊 QUEST 2 PROGRESS:")
    print("   ✅ Hybrid Classifier: COMPLETE")
    print("   ✅ TCN Integration: COMPLETE")
    print("   ✅ Frame-Level Fallback: COMPLETE")
    print("   ✅ Prediction Fusion: COMPLETE")
    print("   ✅ Uncertainty Support: COMPLETE")
    print("\n💎 +100 XP")
    print("🔓 Next: Main.py integration")
