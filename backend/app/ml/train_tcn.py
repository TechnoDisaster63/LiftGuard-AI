"""
LiftGuard AI - TCN Training Script
==================================
 
QUEST 3: Train the Temporal Convolutional Network
 
This script:
1. Generates realistic temporal training sequences
2. Trains the TCN model
3. Validates performance
4. Saves trained weights
 
Usage:
    python train_tcn.py
 
Training data:
- 5,000 sequences (64 frames each)
- 320,000 total frames
- 4 risk classes (SAFE, LOW, MEDIUM, HIGH)
- Realistic fatigue degradation patterns
"""
 
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, f1_score
import time
import os
from datetime import datetime
 
# Import TCN model
from .tcn_model import TemporalConvolutionalNetwork, TCNRiskClassifier
 
# ============================================
# TEMPORAL SEQUENCE GENERATOR
# ============================================
 
class BiomechanicalSequenceGenerator:
    """
    Generates realistic temporal sequences of biomechanical features.
    
    Each sequence represents a realistic lifting pattern with:
    - Fatigue-induced degradation
    - Movement phases (standing → down → up → standing)
    - Individual variation
    - Risk progression
    """
    
    def __init__(self, sequence_length=64, num_features=11):
        self.sequence_length = sequence_length
        self.num_features = num_features
        
        # Feature names for reference
        self.feature_names = [
            'spine_flexion',
            'hip_hinge_angle',
            'knee_asymmetry',
            'stability_index',
            'spinal_load_index',
            'spine_lateral_tilt',
            'left_knee_angle',
            'right_knee_angle',
            'knee_valgus_left',
            'knee_valgus_right',
            'stance_width'
        ]
    
    def generate_sequence(self, risk_level, with_fatigue=True):
        """
        Generate one temporal sequence.
        
        Args:
            risk_level: 0 (SAFE), 1 (LOW), 2 (MEDIUM), 3 (HIGH)
            with_fatigue: Include fatigue-induced degradation
        
        Returns:
            sequence: (sequence_length, num_features) array
            label: risk_level
        """
        sequence = np.zeros((self.sequence_length, self.num_features), dtype=np.float32)
        
        # Base risk parameters
        if risk_level == 0:  # SAFE
            base_spine = np.random.uniform(8, 22)
            base_hip = np.random.uniform(155, 175)
            base_stability = np.random.uniform(0.8, 0.95)
            degradation_rate = 0.0
        
        elif risk_level == 1:  # LOW_RISK
            base_spine = np.random.uniform(22, 32)
            base_hip = np.random.uniform(130, 155)
            base_stability = np.random.uniform(0.65, 0.8)
            degradation_rate = 0.02
        
        elif risk_level == 2:  # MEDIUM_RISK
            base_spine = np.random.uniform(32, 45)
            base_hip = np.random.uniform(100, 130)
            base_stability = np.random.uniform(0.5, 0.65)
            degradation_rate = 0.05
        
        else:  # HIGH_RISK
            base_spine = np.random.uniform(45, 65)
            base_hip = np.random.uniform(60, 100)
            base_stability = np.random.uniform(0.3, 0.5)
            degradation_rate = 0.08
        
        # Generate movement pattern
        # Simulate: standing → bend down → hold → come up → standing
        
        for t in range(self.sequence_length):
            # Movement phase (0-1, represents position in movement)
            phase = (t % 32) / 32.0  # 32-frame movement cycle
            
            if phase < 0.25:  # Standing
                movement_factor = 0.0
            elif phase < 0.5:  # Going down
                movement_factor = (phase - 0.25) / 0.25
            elif phase < 0.75:  # At bottom
                movement_factor = 1.0
            else:  # Coming up
                movement_factor = 1.0 - ((phase - 0.75) / 0.25)
            
            # Fatigue factor (increases over time)
            if with_fatigue:
                fatigue = t / self.sequence_length * degradation_rate
            else:
                fatigue = 0.0
            
            # Feature 0: spine_flexion
            spine = base_spine + movement_factor * base_spine * 0.8 + fatigue * 10
            spine += np.random.normal(0, 2)  # Noise
            sequence[t, 0] = np.clip(spine, 0, 90)
            
            # Feature 1: hip_hinge_angle
            hip = base_hip - movement_factor * 50 - fatigue * 10
            hip += np.random.normal(0, 3)
            sequence[t, 1] = np.clip(hip, 30, 180)
            
            # Feature 2: knee_asymmetry
            asym = np.random.uniform(3, 8) * (1 + fatigue * 2)
            asym += movement_factor * np.random.uniform(2, 5)
            sequence[t, 2] = np.clip(asym, 0, 50)
            
            # Feature 3: stability_index
            stability = base_stability - movement_factor * 0.15 - fatigue * 0.2
            stability += np.random.normal(0, 0.05)
            sequence[t, 3] = np.clip(stability, 0, 1)
            
            # Feature 4: spinal_load_index
            load = (spine / 90) * (1 - stability)
            load += fatigue * 0.1
            sequence[t, 4] = np.clip(load, 0, 1)
            
            # Feature 5: spine_lateral_tilt
            tilt = np.random.uniform(1, 5) + fatigue * 3
            sequence[t, 5] = np.clip(tilt, 0, 35)
            
            # Feature 6-7: knee_angles
            base_knee = 175 - movement_factor * 60
            sequence[t, 6] = np.clip(base_knee + np.random.normal(0, 3), 60, 180)
            sequence[t, 7] = np.clip(base_knee + np.random.normal(0, 3), 60, 180)
            
            # Feature 8-9: knee_valgus
            valgus = -5 * (risk_level + 1) - fatigue * 5
            sequence[t, 8] = np.clip(valgus + np.random.normal(0, 2), -30, 30)
            sequence[t, 9] = np.clip(valgus + np.random.normal(0, 2), -30, 30)
            
            # Feature 10: stance_width
            stance = 0.2 - fatigue * 0.05 + np.random.normal(0, 0.02)
            sequence[t, 10] = np.clip(stance, 0.1, 0.4)
        
        return sequence, risk_level
    
    def generate_dataset(self, num_sequences=5000, class_distribution=None):
        """
        Generate full dataset of temporal sequences.
        
        Args:
            num_sequences: Total number of sequences to generate
            class_distribution: Dict of class proportions (default: balanced)
        
        Returns:
            X: (num_sequences, sequence_length, num_features) array
            y: (num_sequences,) array of labels
        """
        if class_distribution is None:
            # Slightly imbalanced (more SAFE, fewer HIGH_RISK)
            class_distribution = {0: 0.4, 1: 0.3, 2: 0.2, 3: 0.1}
        
        X = []
        y = []
        
        for risk_level, proportion in class_distribution.items():
            n_class = int(num_sequences * proportion)
            
            for _ in range(n_class):
                # 70% with fatigue, 30% without
                with_fatigue = np.random.random() < 0.7
                sequence, label = self.generate_sequence(risk_level, with_fatigue)
                
                X.append(sequence)
                y.append(label)
        
        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int64)
        
        # Shuffle
        indices = np.random.permutation(len(X))
        X = X[indices]
        y = y[indices]
        
        print(f"✅ Generated {len(X)} temporal sequences")
        print(f"   Sequence shape: {X.shape}")
        print(f"   Class distribution: {dict(zip(*np.unique(y, return_counts=True)))}")
        
        return X, y
 
 
# ============================================
# PYTORCH DATASET
# ============================================
 
class TemporalDataset(Dataset):
    """PyTorch Dataset for temporal sequences."""
    
    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        self.y = torch.LongTensor(y)
    
    def __len__(self):
        return len(self.X)
    
    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]
 
 
# ============================================
# TRAINING FUNCTION
# ============================================
 
def train_tcn_model(
    model,
    train_loader,
    val_loader,
    num_epochs=50,
    learning_rate=0.001,
    device='cpu',
    patience=10
):
    """
    Train the TCN model.
    
    Args:
        model: TCN model
        train_loader: Training data loader
        val_loader: Validation data loader
        num_epochs: Maximum number of epochs
        learning_rate: Learning rate
        device: 'cpu' or 'cuda'
        patience: Early stopping patience
    
    Returns:
        model: Trained model
        history: Training history
    """
    print("\n" + "="*60)
    print("🚀 TRAINING TCN MODEL")
    print("="*60)
    
    model = model.to(device)
    
    # Loss and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', patience=5, factor=0.5)
    
    # Training history
    history = {
        'train_loss': [],
        'train_acc': [],
        'val_loss': [],
        'val_acc': []
    }
    
    best_val_loss = float('inf')
    patience_counter = 0
    best_model_state = None
    
    # Training loop
    for epoch in range(num_epochs):
        start_time = time.time()
        
        # ============================================
        # TRAINING PHASE
        # ============================================
        
        model.train()
        train_loss = 0
        train_correct = 0
        train_total = 0
        
        for batch_X, batch_y in train_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)
            
            # Forward pass
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            
            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            # Statistics
            train_loss += loss.item()
            _, predicted = outputs.max(1)
            train_total += batch_y.size(0)
            train_correct += predicted.eq(batch_y).sum().item()
        
        avg_train_loss = train_loss / len(train_loader)
        train_accuracy = 100. * train_correct / train_total
        
        # ============================================
        # VALIDATION PHASE
        # ============================================
        
        model.eval()
        val_loss = 0
        val_correct = 0
        val_total = 0
        
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X = batch_X.to(device)
                batch_y = batch_y.to(device)
                
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                
                val_loss += loss.item()
                _, predicted = outputs.max(1)
                val_total += batch_y.size(0)
                val_correct += predicted.eq(batch_y).sum().item()
        
        avg_val_loss = val_loss / len(val_loader)
        val_accuracy = 100. * val_correct / val_total
        
        # Learning rate scheduling
        scheduler.step(avg_val_loss)
        
        # Store history
        history['train_loss'].append(avg_train_loss)
        history['train_acc'].append(train_accuracy)
        history['val_loss'].append(avg_val_loss)
        history['val_acc'].append(val_accuracy)
        
        # Print progress
        epoch_time = time.time() - start_time
        print(f"Epoch [{epoch+1}/{num_epochs}] ({epoch_time:.1f}s)")
        print(f"  Train Loss: {avg_train_loss:.4f} | Train Acc: {train_accuracy:.2f}%")
        print(f"  Val Loss:   {avg_val_loss:.4f} | Val Acc:   {val_accuracy:.2f}%")
        
        # Early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            patience_counter = 0
            best_model_state = model.state_dict().copy()
            print("  ⭐ Best model so far!")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"\n⏹️ Early stopping triggered (patience={patience})")
                break
    
    # Restore best model
    if best_model_state:
        model.load_state_dict(best_model_state)
        print("\n✅ Restored best model from training")
    
    return model, history
 
 
# ============================================
# EVALUATION FUNCTION
# ============================================
 
def evaluate_model(model, test_loader, device='cpu'):
    """
    Evaluate trained model on test set.
    
    Returns:
        metrics: Dictionary with accuracy, f1, confusion matrix, etc.
    """
    print("\n" + "="*60)
    print("📊 EVALUATING MODEL")
    print("="*60)
    
    model.eval()
    model = model.to(device)
    
    all_preds = []
    all_labels = []
    
    with torch.no_grad():
        for batch_X, batch_y in test_loader:
            batch_X = batch_X.to(device)
            
            outputs = model(batch_X)
            _, predicted = outputs.max(1)
            
            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(batch_y.numpy())
    
    # Calculate metrics
    accuracy = accuracy_score(all_labels, all_preds)
    f1 = f1_score(all_labels, all_preds, average='weighted')
    
    print(f"\n📈 Test Accuracy: {accuracy*100:.2f}%")
    print(f"📈 Test F1-Score: {f1:.4f}")
    
    # Classification report
    print("\n📋 Classification Report:")
    print("-" * 60)
    class_names = ['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK']
    print(classification_report(all_labels, all_preds, target_names=class_names))
    
    # Confusion matrix
    print("🔢 Confusion Matrix:")
    print("-" * 60)
    cm = confusion_matrix(all_labels, all_preds)
    print(cm)
    
    return {
        'accuracy': accuracy,
        'f1_score': f1,
        'confusion_matrix': cm,
        'predictions': all_preds,
        'labels': all_labels
    }
 
 
# ============================================
# PLOTTING FUNCTION
# ============================================
 
def plot_training_history(history, save_path='models/tcn_training_history.png'):
    """Plot training history."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    
    epochs = range(1, len(history['train_loss']) + 1)
    
    # Loss plot
    ax1.plot(epochs, history['train_loss'], 'b-', label='Train Loss')
    ax1.plot(epochs, history['val_loss'], 'r-', label='Val Loss')
    ax1.set_xlabel('Epoch')
    ax1.set_ylabel('Loss')
    ax1.set_title('Training and Validation Loss')
    ax1.legend()
    ax1.grid(True)
    
    # Accuracy plot
    ax2.plot(epochs, history['train_acc'], 'b-', label='Train Acc')
    ax2.plot(epochs, history['val_acc'], 'r-', label='Val Acc')
    ax2.set_xlabel('Epoch')
    ax2.set_ylabel('Accuracy (%)')
    ax2.set_title('Training and Validation Accuracy')
    ax2.legend()
    ax2.grid(True)
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    print(f"\n📊 Training history saved to {save_path}")
    plt.close()
 
 
# ============================================
# MAIN TRAINING PIPELINE
# ============================================
 
def main():
    print("\n" + "🏋️"*30)
    print("\n   LIFTGUARD AI - TCN TRAINING PIPELINE")
    print("\n" + "🏋️"*30)
    
    # Configuration
    NUM_SEQUENCES = 5000
    SEQUENCE_LENGTH = 64
    NUM_FEATURES = 11
    NUM_CLASSES = 4
    BATCH_SIZE = 32
    NUM_EPOCHS = 50
    LEARNING_RATE = 0.001
    
    # Device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"\n🖥️  Device: {device}")
    
    # ============================================
    # STEP 1: GENERATE DATA
    # ============================================
    
    print("\n" + "="*60)
    print("📊 STEP 1: GENERATING TRAINING DATA")
    print("="*60)
    
    generator = BiomechanicalSequenceGenerator(
        sequence_length=SEQUENCE_LENGTH,
        num_features=NUM_FEATURES
    )
    
    X, y = generator.generate_dataset(
        num_sequences=NUM_SEQUENCES,
        class_distribution={0: 0.4, 1: 0.3, 2: 0.2, 3: 0.1}
    )
    
    # Train/Val/Test split
    X_temp, X_test, y_temp, y_test = train_test_split(X, y, test_size=0.15, stratify=y, random_state=42)
    X_train, X_val, y_train, y_val = train_test_split(X_temp, y_temp, test_size=0.15, stratify=y_temp, random_state=42)
    
    print("\n📦 Data Split:")
    print(f"   Training:   {len(X_train)} sequences")
    print(f"   Validation: {len(X_val)} sequences")
    print(f"   Test:       {len(X_test)} sequences")
    
    # Create datasets and dataloaders
    train_dataset = TemporalDataset(X_train, y_train)
    val_dataset = TemporalDataset(X_val, y_val)
    test_dataset = TemporalDataset(X_test, y_test)
    
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    
    # ============================================
    # STEP 2: CREATE MODEL
    # ============================================
    
    print("\n" + "="*60)
    print("🧠 STEP 2: CREATING TCN MODEL")
    print("="*60)
    
    model = TemporalConvolutionalNetwork(
        num_features=NUM_FEATURES,
        num_classes=NUM_CLASSES,
        num_channels=[32, 32, 32, 16],
        kernel_size=3,
        dropout=0.2
    )
    
    num_params = sum(p.numel() for p in model.parameters())
    print(f"   Model parameters: {num_params:,}")
    print("   Architecture: TCN with 4 dilated conv layers")
    
    # ============================================
    # STEP 3: TRAIN MODEL
    # ============================================
    
    print("\n" + "="*60)
    print("🏋️ STEP 3: TRAINING MODEL")
    print("="*60)
    
    model, history = train_tcn_model(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        num_epochs=NUM_EPOCHS,
        learning_rate=LEARNING_RATE,
        device=device,
        patience=10
    )
    
    # ============================================
    # STEP 4: EVALUATE MODEL
    # ============================================
    
    metrics = evaluate_model(model, test_loader, device)
    
    # ============================================
    # STEP 5: SAVE MODEL
    # ============================================
    
    print("\n" + "="*60)
    print("💾 STEP 5: SAVING MODEL")
    print("="*60)
    
    os.makedirs('models', exist_ok=True)
    
    # Save PyTorch model
    save_path = 'models/tcn_risk_classifier.pth'
    torch.save({
        'model_state_dict': model.state_dict(),
        'num_features': NUM_FEATURES,
        'num_classes': NUM_CLASSES,
        'sequence_length': SEQUENCE_LENGTH,
        'accuracy': metrics['accuracy'],
        'f1_score': metrics['f1_score'],
        'timestamp': datetime.now().isoformat()
    }, save_path)
    
    print(f"\n✅ Model saved to {save_path}")
    print(f"   Accuracy: {metrics['accuracy']*100:.2f}%")
    print(f"   F1-Score: {metrics['f1_score']:.4f}")
    
    # Save using TCNRiskClassifier wrapper
    classifier = TCNRiskClassifier()
    classifier.model = model
    classifier.is_trained = True
    classifier.save(save_path)
    
    # Plot training history
    plot_training_history(history)
    
    # ============================================
    # STEP 6: TEST INTEGRATION
    # ============================================
    
    print("\n" + "="*60)
    print("🧪 STEP 6: TESTING INTEGRATION")
    print("="*60)
    
    # Load and test
    test_classifier = TCNRiskClassifier()
    test_classifier.load(save_path)
    
    # Test single prediction
    test_sequence = X_test[0]
    test_label = y_test[0]
    
    result = test_classifier.predict(sequence=test_sequence)
    
    print("\n📝 Test Prediction:")
    print(f"   True label: {['SAFE', 'LOW_RISK', 'MEDIUM_RISK', 'HIGH_RISK'][test_label]}")
    print(f"   Predicted:  {result['risk_label']}")
    print(f"   Confidence: {result['confidence']:.1%}")
    print(f"   ✅ {'CORRECT' if result['risk_level'] == test_label else 'INCORRECT'}")
    
    print("\n" + "="*60)
    print("🎉 TRAINING COMPLETE!")
    print("="*60)
    print("\n📊 Summary:")
    print(f"   Total sequences trained: {NUM_SEQUENCES}")
    print(f"   Final test accuracy: {metrics['accuracy']*100:.2f}%")
    print(f"   Model saved: {save_path}")
    print("\n💡 Next steps:")
    print("   1. Run: python main.py")
    print("   2. Look for 'TCN' badge (should turn GREEN)")
    print("   3. Watch mode switch from 'FRM' to 'HYB' to 'TCN'")
    print("\n🎮 The TCN is now ACTIVE in your system!")
 
 
if __name__ == "__main__":
    main()
