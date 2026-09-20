"""
LiftGuard AI - Advanced ML Training Module
Efficient training with multiple models, cross-validation, and optimization.
 
This module provides:
1. Realistic synthetic data generation based on biomechanics research
2. Multiple ML models (Random Forest, Gradient Boosting, SVM, Neural Network)
3. Ensemble voting for better accuracy
4. Cross-validation to prevent overfitting
5. Hyperparameter optimization
6. Feature importance analysis
"""
 
import numpy as np
import warnings
warnings.filterwarnings('ignore')
 
from sklearn.ensemble import (
    RandomForestClassifier, 
    GradientBoostingClassifier,
    VotingClassifier,
    AdaBoostClassifier
)
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
 
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import (
    train_test_split, 
    cross_val_score,
    GridSearchCV,
    StratifiedKFold
)
from sklearn.metrics import (
    classification_report, 
    accuracy_score,
    f1_score
)
 
import joblib
import os
from datetime import datetime
 
 
class BiomechanicsDataGenerator:
    """
    Generates realistic synthetic biomechanical data based on research.
    
    Reference values from ergonomics literature:
    - NIOSH Lifting Equation
    - OSHA Guidelines
    - Biomechanics research papers
    """
    
    def __init__(self, seed=42):
        np.random.seed(seed)
        
        # ============================================
        # REALISTIC THRESHOLD RANGES (from research)
        # ============================================
        
        # Spine flexion thresholds (degrees)
        # Source: NIOSH guidelines suggest <30° for safe lifting
        self.spine_ranges = {
            'safe': (0, 22),           # Standing or minimal bend
            'low_risk': (22, 35),       # Acceptable bend
            'medium_risk': (35, 50),    # Concerning
            'high_risk': (50, 90)       # Dangerous
        }
        
        # Hip hinge angle (degrees) - higher = more upright
        self.hip_ranges = {
            'safe': (145, 180),
            'low_risk': (115, 145),
            'medium_risk': (85, 115),
            'high_risk': (30, 85)
        }
        
        # Knee asymmetry (degrees difference between legs)
        self.knee_asym_ranges = {
            'safe': (0, 8),
            'low_risk': (8, 15),
            'medium_risk': (15, 25),
            'high_risk': (25, 50)
        }
        
        # Stability index (0-1, higher = more stable)
        self.stability_ranges = {
            'safe': (0.75, 1.0),
            'low_risk': (0.6, 0.75),
            'medium_risk': (0.45, 0.6),
            'high_risk': (0.1, 0.45)
        }
        
        # Spinal load index (0-1, higher = more load)
        self.load_ranges = {
            'safe': (0, 0.35),
            'low_risk': (0.35, 0.55),
            'medium_risk': (0.55, 0.75),
            'high_risk': (0.75, 1.0)
        }
        
        # Additional features for richer data
        self.lateral_tilt_ranges = {
            'safe': (0, 5),
            'low_risk': (5, 10),
            'medium_risk': (10, 18),
            'high_risk': (18, 35)
        }
        
        self.knee_valgus_ranges = {
            'safe': (-5, 5),
            'low_risk': (-10, -5),  # or (5, 10)
            'medium_risk': (-18, -10),
            'high_risk': (-30, -18)
        }
    
    def _sample_from_range(self, range_tuple, noise_std=0.1):
        """Sample a value from a range with some noise."""
        low, high = range_tuple
        mean = (low + high) / 2
        std = (high - low) / 4  # 95% within range
        
        value = np.random.normal(mean, std)
        
        # Add extra noise for realism
        value += np.random.normal(0, noise_std * (high - low))
        
        # Soft clamp (allow slight overflow for realism)
        return np.clip(value, low - (high-low)*0.1, high + (high-low)*0.1)
    
    def generate_sample(self, risk_level):
        """
        Generate a single realistic sample for a given risk level.
        
        Args:
            risk_level: 0 (safe), 1 (low), 2 (medium), 3 (high)
        
        Returns:
            Dictionary of features
        """
        level_names = ['safe', 'low_risk', 'medium_risk', 'high_risk']
        level_name = level_names[risk_level]
        
        # Core features
        spine = self._sample_from_range(self.spine_ranges[level_name])
        hip = self._sample_from_range(self.hip_ranges[level_name])
        knee_asym = self._sample_from_range(self.knee_asym_ranges[level_name])
        stability = self._sample_from_range(self.stability_ranges[level_name])
        load = self._sample_from_range(self.load_ranges[level_name])
        
        # Additional features
        lateral_tilt = self._sample_from_range(self.lateral_tilt_ranges[level_name])
        
        # Knee angles (realistic range: 90-180 degrees)
        base_knee = np.random.uniform(140, 175) if risk_level < 2 else np.random.uniform(100, 150)
        left_knee = base_knee + np.random.normal(0, 3)
        right_knee = base_knee + np.random.normal(0, 3) + knee_asym * np.random.choice([-1, 1])
        
        # Knee valgus (inward collapse)
        if risk_level < 2:
            valgus_left = np.random.normal(0, 3)
            valgus_right = np.random.normal(0, 3)
        else:
            valgus_left = np.random.normal(-8, 5) * (risk_level - 1)
            valgus_right = np.random.normal(-8, 5) * (risk_level - 1)
        
        # Shoulder symmetry
        shoulder_sym = np.random.uniform(0, 0.05) if risk_level == 0 else np.random.uniform(0, 0.1 * (risk_level + 1))
        
        # Arm extension
        arm_ext_left = np.random.uniform(100, 200) + risk_level * 30
        arm_ext_right = np.random.uniform(100, 200) + risk_level * 30
        
        # Stance width (normalized)
        stance = np.random.uniform(0.15, 0.3) if risk_level < 2 else np.random.uniform(0.1, 0.25)
        
        # Movement smoothness (1 = smooth, 0 = jerky)
        smoothness = np.random.uniform(0.7, 1.0) if risk_level == 0 else np.random.uniform(0.3, 0.8) / (risk_level + 1)
        
        # Velocity (higher = faster movement)
        velocity = np.random.uniform(0.1, 0.5) if risk_level < 2 else np.random.uniform(0.3, 1.0)
        
        return {
            'spine_flexion': max(0, spine),
            'hip_hinge_angle': np.clip(hip, 30, 180),
            'knee_asymmetry': max(0, knee_asym),
            'stability_index': np.clip(stability, 0, 1),
            'spinal_load_index': np.clip(load, 0, 1),
            'spine_lateral_tilt': max(0, lateral_tilt),
            'left_knee_angle': np.clip(left_knee, 60, 180),
            'right_knee_angle': np.clip(right_knee, 60, 180),
            'knee_valgus_left': valgus_left,
            'knee_valgus_right': valgus_right,
            'shoulder_symmetry': max(0, shoulder_sym),
            'left_arm_extension': arm_ext_left,
            'right_arm_extension': arm_ext_right,
            'stance_width': stance,
            'movement_smoothness': np.clip(smoothness, 0, 1),
            'movement_velocity': velocity
        }
    
    def generate_dataset(self, n_samples=5000, class_distribution=None):
        """
        Generate a complete dataset with balanced or custom class distribution.
        
        Args:
            n_samples: Total number of samples
            class_distribution: Dict like {0: 0.4, 1: 0.3, 2: 0.2, 3: 0.1}
        
        Returns:
            X (features array), y (labels array), feature_names
        """
        if class_distribution is None:
            # Default: slightly imbalanced (more safe samples, fewer dangerous)
            class_distribution = {0: 0.35, 1: 0.30, 2: 0.20, 3: 0.15}
        
        X = []
        y = []
        
        for risk_level, proportion in class_distribution.items():
            n_class_samples = int(n_samples * proportion)
            
            for _ in range(n_class_samples):
                sample = self.generate_sample(risk_level)
                X.append(list(sample.values()))
                y.append(risk_level)
        
        # Shuffle
        indices = np.random.permutation(len(X))
        X = np.array(X)[indices]
        y = np.array(y)[indices]
        
        feature_names = list(self.generate_sample(0).keys())
        
        print(f"✅ Generated {len(X)} samples")
        print(f"   Class distribution: {dict(zip(*np.unique(y, return_counts=True)))}")
        
        return X, y, feature_names
 
 
class AdvancedRiskClassifier:
    """
    Advanced ML classifier with multiple models and ensemble voting.
    """
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.models = {}
        self.ensemble = None
        self.best_model = None
        self.best_model_name = None
        self.feature_names = None
        self.feature_importance = None
        self.is_trained = False
        
        # Training history
        self.training_history = {
            'accuracy': {},
            'f1_score': {},
            'cv_scores': {}
        }
        
        print("🧠 Advanced Risk Classifier initialized")
    
    def _create_models(self):
        """Create multiple ML models for comparison."""
        
        self.models = {
            # Random Forest - good for tabular data
            'random_forest': RandomForestClassifier(
                n_estimators=200,
                max_depth=15,
                min_samples_split=5,
                min_samples_leaf=2,
                max_features='sqrt',
                class_weight='balanced',
                random_state=42,
                n_jobs=-1
            ),
            
            # Gradient Boosting - often best performance
            'gradient_boosting': GradientBoostingClassifier(
                n_estimators=150,
                max_depth=8,
                learning_rate=0.1,
                min_samples_split=5,
                min_samples_leaf=2,
                subsample=0.8,
                random_state=42
            ),
            
            # AdaBoost - good for imbalanced data
            'adaboost': AdaBoostClassifier(
                n_estimators=100,
                learning_rate=0.5,
                random_state=42
            ),
            
            # Support Vector Machine - good for complex boundaries
            'svm': SVC(
                C=1.0,
                kernel='rbf',
                gamma='scale',
                class_weight='balanced',
                probability=True,
                random_state=42
            ),
            
            # K-Nearest Neighbors - simple but effective
            'knn': KNeighborsClassifier(
                n_neighbors=7,
                weights='distance',
                metric='minkowski',
                n_jobs=-1
            ),
            
            # Neural Network (MLP) - can learn complex patterns
            'neural_network': MLPClassifier(
                hidden_layer_sizes=(128, 64, 32),
                activation='relu',
                solver='adam',
                alpha=0.001,
                learning_rate='adaptive',
                max_iter=500,
                early_stopping=True,
                validation_fraction=0.1,
                random_state=42
            ),
            
            # Logistic Regression - baseline
            'logistic_regression': LogisticRegression(
                C=1.0,
                class_weight='balanced',
                max_iter=1000,
                random_state=42,
                n_jobs=-1
            )
        }
        
        print(f"   Created {len(self.models)} models for training")
    
    def train(self, X, y, feature_names=None, test_size=0.2, cv_folds=5):
        """
        Train all models and select the best one.
        
        Args:
            X: Feature matrix
            y: Labels
            feature_names: List of feature names
            test_size: Proportion for test set
            cv_folds: Number of cross-validation folds
        """
        print("\n" + "="*60)
        print("🚀 TRAINING ADVANCED ML MODELS")
        print("="*60)
        
        self.feature_names = feature_names
        
        # Create models
        self._create_models()
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, stratify=y, random_state=42
        )
        
        print("\n📊 Data Split:")
        print(f"   Training: {len(X_train)} samples")
        print(f"   Testing: {len(X_test)} samples")
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train and evaluate each model
        print(f"\n🏋️ Training {len(self.models)} models with {cv_folds}-fold cross-validation...")
        print("-" * 60)
        
        results = []
        
        for name, model in self.models.items():
            print(f"\n   Training {name}...", end=" ")
            
            try:
                # Cross-validation
                cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
                cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=cv, scoring='f1_weighted')
                
                # Train on full training set
                model.fit(X_train_scaled, y_train)
                
                # Evaluate on test set
                y_pred = model.predict(X_test_scaled)
                accuracy = accuracy_score(y_test, y_pred)
                f1 = f1_score(y_test, y_pred, average='weighted')
                
                # Store results
                self.training_history['accuracy'][name] = accuracy
                self.training_history['f1_score'][name] = f1
                self.training_history['cv_scores'][name] = cv_scores.mean()
                
                results.append({
                    'name': name,
                    'accuracy': accuracy,
                    'f1_score': f1,
                    'cv_mean': cv_scores.mean(),
                    'cv_std': cv_scores.std()
                })
                
                print(f"✅ Acc: {accuracy:.3f}, F1: {f1:.3f}, CV: {cv_scores.mean():.3f} (±{cv_scores.std():.3f})")
                
            except Exception as e:
                print(f"❌ Failed: {e}")
        
        # Find best model
        print("\n" + "-" * 60)
        
        # Sort by F1 score
        results.sort(key=lambda x: x['f1_score'], reverse=True)
        
        print("\n🏆 MODEL RANKING (by F1 Score):")
        for i, r in enumerate(results):
            marker = "👑" if i == 0 else f"{i+1}."
            print(f"   {marker} {r['name']}: F1={r['f1_score']:.4f}, Acc={r['accuracy']:.4f}")
        
        # Select best model
        self.best_model_name = results[0]['name']
        self.best_model = self.models[self.best_model_name]
        
        print(f"\n✅ Best Model: {self.best_model_name}")
        print(f"   Accuracy: {results[0]['accuracy']:.4f}")
        print(f"   F1 Score: {results[0]['f1_score']:.4f}")
        
        # Create ensemble from top 3 models
        self._create_ensemble(X_train_scaled, y_train, X_test_scaled, y_test)
        
        # Calculate feature importance
        self._calculate_feature_importance(X_train_scaled, y_train)
        
        # Detailed report for best model
        print(f"\n📋 Classification Report ({self.best_model_name}):")
        print("-" * 60)
        y_pred = self.best_model.predict(X_test_scaled)
        print(classification_report(y_test, y_pred, 
                                   target_names=['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK']))
        
        self.is_trained = True
        print("\n" + "="*60)
        print("✅ TRAINING COMPLETE!")
        print("="*60)
        
        return self
    
    def _create_ensemble(self, X_train, y_train, X_test, y_test):
        """Create an ensemble from top performing models."""
        print("\n🎭 Creating Ensemble Model...")
        
        # Get top 3 models by F1 score
        sorted_models = sorted(
            self.training_history['f1_score'].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        # Create voting ensemble
        estimators = [(name, self.models[name]) for name, _ in sorted_models]
        
        self.ensemble = VotingClassifier(
            estimators=estimators,
            voting='soft'  # Use probability averaging
        )
        
        # Train ensemble
        self.ensemble.fit(X_train, y_train)
        
        # Evaluate
        y_pred = self.ensemble.predict(X_test)
        ensemble_accuracy = accuracy_score(y_test, y_pred)
        ensemble_f1 = f1_score(y_test, y_pred, average='weighted')
        
        print(f"   Ensemble members: {[name for name, _ in sorted_models]}")
        print(f"   Ensemble Accuracy: {ensemble_accuracy:.4f}")
        print(f"   Ensemble F1 Score: {ensemble_f1:.4f}")
        
        # Use ensemble if it's better
        if ensemble_f1 > self.training_history['f1_score'][self.best_model_name]:
            print("   🎉 Ensemble outperforms best single model!")
            self.best_model = self.ensemble
            self.best_model_name = "ensemble"
            self.training_history['f1_score']['ensemble'] = ensemble_f1
            self.training_history['accuracy']['ensemble'] = ensemble_accuracy
    
    def _calculate_feature_importance(self, X_train, y_train):
        """Calculate feature importance using multiple methods."""
        print("\n📊 Calculating Feature Importance...")
        
        importance_scores = {}
        
        # Method 1: Random Forest importance
        if 'random_forest' in self.models:
            rf = self.models['random_forest']
            if hasattr(rf, 'feature_importances_'):
                for i, imp in enumerate(rf.feature_importances_):
                    name = self.feature_names[i] if self.feature_names else f"feature_{i}"
                    importance_scores[name] = importance_scores.get(name, 0) + imp
        
        # Method 2: Gradient Boosting importance
        if 'gradient_boosting' in self.models:
            gb = self.models['gradient_boosting']
            if hasattr(gb, 'feature_importances_'):
                for i, imp in enumerate(gb.feature_importances_):
                    name = self.feature_names[i] if self.feature_names else f"feature_{i}"
                    importance_scores[name] = importance_scores.get(name, 0) + imp
        
        # Average and normalize
        if importance_scores:
            total = sum(importance_scores.values())
            self.feature_importance = {
                k: v / total for k, v in 
                sorted(importance_scores.items(), key=lambda x: x[1], reverse=True)
            }
            
            print("\n   Top 5 Most Important Features:")
            for i, (name, imp) in enumerate(list(self.feature_importance.items())[:5]):
                bar = "█" * int(imp * 50)
                print(f"   {i+1}. {name}: {imp:.4f} {bar}")
    
    def predict(self, features):
        """
        Predict risk level for given features.
        
        Args:
            features: Dict of feature values or array
        
        Returns:
            Dict with prediction, probabilities, confidence
        """
        if not self.is_trained:
            raise ValueError("Model not trained! Call train() first.")
        
        # Convert dict to array if needed
        if isinstance(features, dict):
            if self.feature_names:
                feature_array = np.array([features.get(name, 0) for name in self.feature_names])
            else:
                feature_array = np.array(list(features.values()))
        else:
            feature_array = np.array(features)
        
        # Reshape and scale
        feature_array = feature_array.reshape(1, -1)
        feature_scaled = self.scaler.transform(feature_array)
        
        # Predict
        prediction = self.best_model.predict(feature_scaled)[0]
        
        # Get probabilities
        if hasattr(self.best_model, 'predict_proba'):
            probabilities = self.best_model.predict_proba(feature_scaled)[0]
            confidence = probabilities[prediction]
        else:
            probabilities = [0.25, 0.25, 0.25, 0.25]
            probabilities[prediction] = 1.0
            confidence = 1.0
        
        return {
            'risk_level': int(prediction),
            'risk_label': ['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK'][prediction],
            'confidence': float(confidence),
            'probabilities': probabilities.tolist() if isinstance(probabilities, np.ndarray) else probabilities
        }
    
    def save(self, path='models/advanced_classifier.pkl'):
        """Save the trained model."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        save_data = {
            'scaler': self.scaler,
            'best_model': self.best_model,
            'best_model_name': self.best_model_name,
            'feature_names': self.feature_names,
            'feature_importance': self.feature_importance,
            'training_history': self.training_history,
            'timestamp': datetime.now().isoformat()
        }
        
        joblib.dump(save_data, path)
        print(f"✅ Model saved to {path}")
    
    def load(self, path='models/advanced_classifier.pkl'):
        """Load a trained model."""
        if not os.path.exists(path):
            print(f"❌ Model file not found: {path}")
            return False
        
        data = joblib.load(path)
        
        self.scaler = data['scaler']
        self.best_model = data['best_model']
        self.best_model_name = data['best_model_name']
        self.feature_names = data['feature_names']
        self.feature_importance = data.get('feature_importance')
        self.training_history = data.get('training_history', {})
        self.is_trained = True
        
        print(f"✅ Model loaded from {path}")
        print(f"   Model: {self.best_model_name}")
        print(f"   Trained: {data.get('timestamp', 'Unknown')}")
        
        return True
 
 
class HyperparameterOptimizer:
    """
    Optimize hyperparameters for the best model.
    """
    
    def __init__(self, model_type='random_forest'):
        self.model_type = model_type
        self.best_params = None
        self.best_score = None
        
    def optimize(self, X, y, cv=5, n_iter=50):
        """
        Find optimal hyperparameters using grid/random search.
        """
        print(f"\n🔧 Optimizing {self.model_type} hyperparameters...")
        print("   This may take a few minutes...")
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        if self.model_type == 'random_forest':
            model = RandomForestClassifier(random_state=42, n_jobs=-1)
            param_grid = {
                'n_estimators': [100, 200, 300],
                'max_depth': [10, 15, 20, None],
                'min_samples_split': [2, 5, 10],
                'min_samples_leaf': [1, 2, 4],
                'max_features': ['sqrt', 'log2']
            }
        
        elif self.model_type == 'gradient_boosting':
            model = GradientBoostingClassifier(random_state=42)
            param_grid = {
                'n_estimators': [100, 150, 200],
                'max_depth': [5, 8, 10],
                'learning_rate': [0.05, 0.1, 0.2],
                'min_samples_split': [2, 5],
                'subsample': [0.8, 0.9, 1.0]
            }
        
        elif self.model_type == 'neural_network':
            model = MLPClassifier(random_state=42, early_stopping=True)
            param_grid = {
                'hidden_layer_sizes': [(64, 32), (128, 64), (128, 64, 32)],
                'activation': ['relu', 'tanh'],
                'alpha': [0.0001, 0.001, 0.01],
                'learning_rate': ['constant', 'adaptive']
            }
        
        else:
            print(f"❌ Unknown model type: {self.model_type}")
            return None
        
        # Grid search with cross-validation
        grid_search = GridSearchCV(
            model, 
            param_grid, 
            cv=cv, 
            scoring='f1_weighted',
            n_jobs=-1,
            verbose=1
        )
        
        grid_search.fit(X_scaled, y)
        
        self.best_params = grid_search.best_params_
        self.best_score = grid_search.best_score_
        
        print("\n✅ Optimization Complete!")
        print(f"   Best Score: {self.best_score:.4f}")
        print("   Best Parameters:")
        for param, value in self.best_params.items():
            print(f"      {param}: {value}")
        
        return self.best_params
 
 
def train_and_save_model(n_samples=5000, save_path='models/advanced_classifier.pkl'):
    """
    Complete training pipeline - generate data, train, and save.
    """
    print("\n" + "🏋️"*25)
    print("\n   LIFTGUARD AI - ADVANCED ML TRAINING")
    print("\n" + "🏋️"*25)
    
    # Step 1: Generate data
    print("\n📊 STEP 1: Generating Training Data")
    print("-" * 50)
    
    generator = BiomechanicsDataGenerator(seed=42)
    X, y, feature_names = generator.generate_dataset(n_samples=n_samples)
    
    # Step 2: Train models
    print("\n🧠 STEP 2: Training ML Models")
    print("-" * 50)
    
    classifier = AdvancedRiskClassifier()
    classifier.train(X, y, feature_names=feature_names)
    
    # Step 3: Save model
    print("\n💾 STEP 3: Saving Model")
    print("-" * 50)
    
    classifier.save(save_path)
    
    # Step 4: Test predictions
    print("\n🧪 STEP 4: Testing Predictions")
    print("-" * 50)
    
    test_cases = [
        {
            'name': 'Standing Straight',
            'expected': 'SAFE',
            'features': {
                'spine_flexion': 8,
                'hip_hinge_angle': 172,
                'knee_asymmetry': 2,
                'stability_index': 0.92,
                'spinal_load_index': 0.08,
                'spine_lateral_tilt': 2,
                'left_knee_angle': 175,
                'right_knee_angle': 173,
                'knee_valgus_left': 1,
                'knee_valgus_right': -1,
                'shoulder_symmetry': 0.02,
                'left_arm_extension': 120,
                'right_arm_extension': 118,
                'stance_width': 0.22,
                'movement_smoothness': 0.95,
                'movement_velocity': 0.1
            }
        },
        {
            'name': 'Good Squat',
            'expected': 'SAFE or LOW_RISK',
            'features': {
                'spine_flexion': 20,
                'hip_hinge_angle': 148,
                'knee_asymmetry': 5,
                'stability_index': 0.82,
                'spinal_load_index': 0.25,
                'spine_lateral_tilt': 4,
                'left_knee_angle': 125,
                'right_knee_angle': 120,
                'knee_valgus_left': 2,
                'knee_valgus_right': -2,
                'shoulder_symmetry': 0.03,
                'left_arm_extension': 150,
                'right_arm_extension': 148,
                'stance_width': 0.25,
                'movement_smoothness': 0.85,
                'movement_velocity': 0.3
            }
        },
        {
            'name': 'Dangerous Bend',
            'expected': 'HIGH_RISK',
            'features': {
                'spine_flexion': 58,
                'hip_hinge_angle': 68,
                'knee_asymmetry': 28,
                'stability_index': 0.32,
                'spinal_load_index': 0.88,
                'spine_lateral_tilt': 22,
                'left_knee_angle': 95,
                'right_knee_angle': 120,
                'knee_valgus_left': -18,
                'knee_valgus_right': -12,
                'shoulder_symmetry': 0.15,
                'left_arm_extension': 280,
                'right_arm_extension': 250,
                'stance_width': 0.12,
                'movement_smoothness': 0.25,
                'movement_velocity': 0.8
            }
        }
    ]
    
    for test in test_cases:
        result = classifier.predict(test['features'])
        status = "✅" if test['expected'] in result['risk_label'] or result['risk_label'] in test['expected'] else "⚠️"
        print(f"\n{status} {test['name']}:")
        print(f"   Expected: {test['expected']}")
        print(f"   Got: {result['risk_label']} (confidence: {result['confidence']:.1%})")
    
    print("\n" + "="*60)
    print("🎉 TRAINING PIPELINE COMPLETE!")
    print("="*60)
    
    return classifier
 
 
# Run if executed directly
if __name__ == "__main__":
    classifier = train_and_save_model(n_samples=5000)
