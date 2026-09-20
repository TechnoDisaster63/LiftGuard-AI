"""
LiftGuard AI - Injury Prediction Model
Predicts probability of injury based on cumulative fatigue and form patterns.
"""
 
import numpy as np
from sklearn.linear_model import LogisticRegression
 
 
class InjuryPredictor:
    """
    Predicts probability of injury in upcoming lifts.
    
    Uses cumulative factors:
    - Total workload (number of lifts)
    - Average form quality
    - Current fatigue level
    - Form consistency
    - Movement asymmetry
    """
    
    def __init__(self):
        self.model = LogisticRegression()
        self.trained = False
        
        # Train on research-based synthetic data
        self._train_on_research_data()
        
        print("🏥 Injury Predictor initialized")
    
    def _train_on_research_data(self):
        """
        Train on data synthesized from ergonomics research.
        
        Real-world version would use:
        - OSHA incident reports
        - Insurance claims data
        - Sensor data from workplaces
        """
        np.random.seed(42)
        
        X = []  # Features
        y = []  # Labels (0 = safe, 1 = injury)
        
        # Generate SAFE scenarios (no injury)
        for _ in range(500):
            cumulative_lifts = np.random.randint(1, 50)
            avg_spine_angle = np.random.normal(18, 5)
            fatigue_score = np.random.uniform(70, 100)
            form_variance = np.random.uniform(0, 5)
            asymmetry = np.random.uniform(0, 8)
            
            X.append([cumulative_lifts, avg_spine_angle, fatigue_score, form_variance, asymmetry])
            y.append(0)  # No injury
        
        # Generate RISKY scenarios (injury likely)
        for _ in range(100):
            cumulative_lifts = np.random.randint(100, 300)
            avg_spine_angle = np.random.normal(38, 10)
            fatigue_score = np.random.uniform(20, 50)
            form_variance = np.random.uniform(8, 20)
            asymmetry = np.random.uniform(12, 30)
            
            X.append([cumulative_lifts, avg_spine_angle, fatigue_score, form_variance, asymmetry])
            y.append(1)  # Injury risk
        
        # Train model
        self.model.fit(X, y)
        self.trained = True
        
        print("   Trained on 600 scenarios (500 safe, 100 risky)")
    
    def predict_injury_risk(self, cumulative_lifts, avg_spine_angle, 
                           fatigue_score, form_variance, asymmetry):
        """
        Predict probability of injury in next 10 lifts.
        
        Args:
            cumulative_lifts: Total lifts done in session
            avg_spine_angle: Average spine flexion angle
            fatigue_score: Current fatigue score (0-100)
            form_variance: How consistent is form
            asymmetry: Movement asymmetry score
            
        Returns:
            Dictionary with probability, category, and recommendations
        """
        features = [[cumulative_lifts, avg_spine_angle, fatigue_score, form_variance, asymmetry]]
        
        # Get probability
        prob = self.model.predict_proba(features)[0][1]
        
        # Determine category and action
        if prob < 0.15:
            category = "LOW"
            action = "✅ Continue with normal caution"
        elif prob < 0.35:
            category = "MODERATE"
            action = "⚠️ Review form, consider break soon"
        elif prob < 0.60:
            category = "HIGH"
            action = "🔶 Take a break within 5 lifts"
        else:
            category = "CRITICAL"
            action = "🛑 STOP IMMEDIATELY - High injury risk"
        
        return {
            'probability': round(prob * 100, 1),
            'category': category,
            'action': action,
            'contributing_factors': self._explain_risk(
                cumulative_lifts, avg_spine_angle, fatigue_score, form_variance, asymmetry
            )
        }
    
    def _explain_risk(self, lifts, angle, fatigue, variance, asymmetry):
        """
        Explain why the risk is what it is.
        Transparency builds trust!
        """
        factors = []
        
        if lifts > 150:
            factors.append(f"📊 High cumulative workload ({lifts} lifts)")
        
        if angle > 30:
            factors.append(f"📐 Excessive spine flexion ({angle:.1f}°)")
        
        if fatigue < 50:
            factors.append(f"😓 Significant fatigue ({100-fatigue:.0f}% fatigued)")
        
        if variance > 10:
            factors.append(f"📉 Inconsistent form (variance: {variance:.1f})")
        
        if asymmetry > 15:
            factors.append(f"↔️ Movement asymmetry ({asymmetry:.1f})")
        
        if not factors:
            factors.append("✅ All indicators within normal range")
        
        return factors
 
 
# Test if run directly
if __name__ == "__main__":
    print("Testing Injury Predictor...")
    print("-" * 40)
    
    predictor = InjuryPredictor()
    
    # Test SAFE scenario
    print("\n🟢 SAFE SCENARIO:")
    print("   20 lifts, good form, fresh")
    result = predictor.predict_injury_risk(
        cumulative_lifts=20,
        avg_spine_angle=20,
        fatigue_score=85,
        form_variance=3,
        asymmetry=5
    )
    print(f"   Risk: {result['probability']}% ({result['category']})")
    print(f"   Action: {result['action']}")
    
    # Test MODERATE scenario
    print("\n🟡 MODERATE SCENARIO:")
    print("   80 lifts, some fatigue")
    result = predictor.predict_injury_risk(
        cumulative_lifts=80,
        avg_spine_angle=28,
        fatigue_score=60,
        form_variance=7,
        asymmetry=10
    )
    print(f"   Risk: {result['probability']}% ({result['category']})")
    print(f"   Action: {result['action']}")
    
    # Test RISKY scenario
    print("\n🔴 RISKY SCENARIO:")
    print("   150 lifts, poor form, very fatigued")
    result = predictor.predict_injury_risk(
        cumulative_lifts=150,
        avg_spine_angle=40,
        fatigue_score=35,
        form_variance=15,
        asymmetry=20
    )
    print(f"   Risk: {result['probability']}% ({result['category']})")
    print(f"   Action: {result['action']}")
    print("   Contributing factors:")
    for factor in result['contributing_factors']:
        print(f"      {factor}")
    
    print("\n" + "-" * 40)
    print("✅ Injury Predictor Test Complete!")
