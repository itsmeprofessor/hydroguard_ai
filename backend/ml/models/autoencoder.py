"""
Autoencoder Neural Network Models for Anomaly Detection
========================================================
This module implements:
1. Standard Autoencoder for unsupervised anomaly detection
2. LSTM-Autoencoder for temporal pattern learning
3. Hybrid model combining both approaches
"""

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, Model, regularizers
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from typing import Tuple, Dict, List, Optional, Union
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class WeatherAutoencoder:
    """
    Autoencoder Neural Network for Weather Anomaly Detection.
    
    Architecture:
    - Encoder: Input -> Dense layers with decreasing units -> Latent space
    - Decoder: Latent space -> Dense layers with increasing units -> Reconstruction
    
    The model learns to reconstruct normal weather patterns. Anomalies are detected
    by measuring reconstruction error - high error indicates unusual patterns.
    """
    
    def __init__(
        self,
        input_dim: int,
        encoding_dim: int = 8,
        hidden_layers: List[int] = [64, 32, 16],
        dropout_rate: float = 0.2,
        learning_rate: float = 0.001,
        l2_regularization: float = 0.0001
    ):
        """
        Initialize the Autoencoder.
        
        Args:
            input_dim: Number of input features
            encoding_dim: Dimension of latent space (bottleneck)
            hidden_layers: List of hidden layer sizes for encoder
            dropout_rate: Dropout rate for regularization
            learning_rate: Learning rate for optimizer
            l2_regularization: L2 regularization strength
        """
        self.input_dim = input_dim
        self.encoding_dim = encoding_dim
        self.hidden_layers = hidden_layers
        self.dropout_rate = dropout_rate
        self.learning_rate = learning_rate
        self.l2_regularization = l2_regularization
        
        self.model: Optional[Model] = None
        self.encoder: Optional[Model] = None
        self.decoder: Optional[Model] = None
        self.history: Optional[dict] = None
        
        # Anomaly detection thresholds
        self.threshold: Optional[float] = None
        self.mean_error: Optional[float] = None
        self.std_error: Optional[float] = None
        
        self._build_model()
    
    def _build_model(self) -> None:
        """Build the autoencoder architecture."""
        logger.info(f"Building Autoencoder: input_dim={self.input_dim}, "
                   f"encoding_dim={self.encoding_dim}, layers={self.hidden_layers}")
        
        # L2 regularizer
        reg = regularizers.l2(self.l2_regularization)
        
        # === ENCODER ===
        encoder_input = layers.Input(shape=(self.input_dim,), name='encoder_input')
        x = encoder_input
        
        for i, units in enumerate(self.hidden_layers):
            x = layers.Dense(
                units, 
                activation='relu',
                kernel_regularizer=reg,
                name=f'encoder_dense_{i}'
            )(x)
            x = layers.BatchNormalization(name=f'encoder_bn_{i}')(x)
            x = layers.Dropout(self.dropout_rate, name=f'encoder_dropout_{i}')(x)
        
        # Latent space
        latent = layers.Dense(
            self.encoding_dim, 
            activation='relu',
            kernel_regularizer=reg,
            name='latent_space'
        )(x)
        
        self.encoder = Model(encoder_input, latent, name='encoder')
        
        # === DECODER ===
        decoder_input = layers.Input(shape=(self.encoding_dim,), name='decoder_input')
        x = decoder_input
        
        # Mirror encoder layers
        for i, units in enumerate(reversed(self.hidden_layers)):
            x = layers.Dense(
                units,
                activation='relu',
                kernel_regularizer=reg,
                name=f'decoder_dense_{i}'
            )(x)
            x = layers.BatchNormalization(name=f'decoder_bn_{i}')(x)
            x = layers.Dropout(self.dropout_rate, name=f'decoder_dropout_{i}')(x)
        
        # Output reconstruction
        decoder_output = layers.Dense(
            self.input_dim,
            activation='linear',
            name='decoder_output'
        )(x)
        
        self.decoder = Model(decoder_input, decoder_output, name='decoder')
        
        # === FULL AUTOENCODER ===
        autoencoder_input = layers.Input(shape=(self.input_dim,), name='autoencoder_input')
        encoded = self.encoder(autoencoder_input)
        decoded = self.decoder(encoded)
        
        self.model = Model(autoencoder_input, decoded, name='autoencoder')
        
        # Compile model
        optimizer = keras.optimizers.Adam(learning_rate=self.learning_rate)
        self.model.compile(
            optimizer=optimizer,
            loss='mse',
            metrics=['mae']
        )
        
        logger.info("Autoencoder model built successfully")
        self.model.summary(print_fn=logger.info)
    
    def train(
        self,
        X_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        epochs: int = 100,
        batch_size: int = 64,
        early_stopping_patience: int = 10,
        checkpoint_path: Optional[str] = None,
        threshold_k: float = 3.0
    ) -> Dict:
        """
        Train the autoencoder model.
        
        Args:
            X_train: Training data
            X_val: Validation data (optional, will split from train if not provided)
            epochs: Number of training epochs
            batch_size: Batch size
            early_stopping_patience: Patience for early stopping
            checkpoint_path: Path to save best model
            threshold_k: Number of standard deviations for anomaly threshold
            
        Returns:
            Training history dictionary
        """
        logger.info(f"Starting training: epochs={epochs}, batch_size={batch_size}")
        
        # Callbacks
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=early_stopping_patience,
                restore_best_weights=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=1e-6,
                verbose=1
            )
        ]
        
        if checkpoint_path:
            callbacks.append(
                ModelCheckpoint(
                    checkpoint_path,
                    monitor='val_loss',
                    save_best_only=True,
                    verbose=1
                )
            )
        
        # Split validation if not provided
        if X_val is None:
            split_idx = int(len(X_train) * 0.8)
            X_val = X_train[split_idx:]
            X_train = X_train[:split_idx]
        
        # Train
        history = self.model.fit(
            X_train, X_train,  # Autoencoder reconstructs input
            validation_data=(X_val, X_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            verbose=1
        )
        
        self.history = history.history
        
        # Calculate anomaly threshold (sigma-based or percentile on training errors)
        self._calculate_threshold(X_train, threshold_k)
        
        logger.info(f"Training complete. Final loss: {history.history['loss'][-1]:.6f}")
        logger.info(f"Anomaly threshold set to: {self.threshold:.6f}")
        
        return self.history

    def train_with_threshold_percentile(
        self,
        X_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        epochs: int = 100,
        batch_size: int = 64,
        early_stopping_patience: int = 10,
        checkpoint_path: Optional[str] = None,
        percentile: float = 95.0,
    ) -> Dict:
        """
        Same as ``train`` but sets the anomaly threshold from the given **percentile**
        of reconstruction errors on **X_train** (top (100-p)% treated as anomalous in expectation).

        Use for per-city models so each city gets a data-driven threshold.
        """
        logger.info(
            f"Starting training (percentile threshold={percentile}): epochs={epochs}, batch_size={batch_size}"
        )
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=early_stopping_patience,
                restore_best_weights=True,
                verbose=1,
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=1e-6,
                verbose=1,
            ),
        ]
        if checkpoint_path:
            callbacks.append(
                ModelCheckpoint(
                    checkpoint_path,
                    monitor='val_loss',
                    save_best_only=True,
                    verbose=1,
                )
            )
        if X_val is None:
            split_idx = int(len(X_train) * 0.8)
            X_val = X_train[split_idx:]
            X_train = X_train[:split_idx]

        history = self.model.fit(
            X_train,
            X_train,
            validation_data=(X_val, X_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            verbose=1,
        )
        self.history = history.history
        self._calculate_threshold_percentile(X_train, percentile)
        logger.info(f"Training complete. Threshold (p{percentile}): {self.threshold:.6f}")
        return self.history
    
    def _calculate_threshold(self, X: np.ndarray, k: float = 3.0) -> None:
        """
        Calculate anomaly detection threshold.
        
        Uses mean + k * std of reconstruction errors on training data.
        
        Args:
            X: Training data
            k: Number of standard deviations
        """
        reconstructions = self.model.predict(X, verbose=0)
        errors = np.mean(np.square(X - reconstructions), axis=1)
        
        self.mean_error = np.mean(errors)
        self.std_error = np.std(errors)
        self.threshold = self.mean_error + k * self.std_error
        
        # Also store percentile thresholds for risk levels
        self.error_percentiles = {
            50: np.percentile(errors, 50),
            75: np.percentile(errors, 75),
            90: np.percentile(errors, 90),
            95: np.percentile(errors, 95),
            99: np.percentile(errors, 99)
        }

    def _calculate_threshold_percentile(self, X: np.ndarray, percentile: float) -> None:
        """
        Set threshold to the given percentile of reconstruction errors on X.

        Example: percentile=95 → ~5% of training days have error above threshold
        (under the training distribution).
        """
        reconstructions = self.model.predict(X, verbose=0)
        errors = np.mean(np.square(X - reconstructions), axis=1)
        p = float(np.clip(percentile, 0.0, 100.0))
        self.mean_error = float(np.mean(errors))
        self.std_error = float(np.std(errors))
        self.threshold = float(np.percentile(errors, p))
        self.error_percentiles = {
            50: float(np.percentile(errors, 50)),
            75: float(np.percentile(errors, 75)),
            90: float(np.percentile(errors, 90)),
            95: float(np.percentile(errors, 95)),
            99: float(np.percentile(errors, 99)),
        }
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Get reconstructions from the model."""
        return self.model.predict(X, verbose=0)
    
    def get_reconstruction_error(self, X: np.ndarray) -> np.ndarray:
        """
        Calculate reconstruction error for each sample.
        
        Args:
            X: Input data
            
        Returns:
            Array of reconstruction errors (MSE)
        """
        reconstructions = self.predict(X)
        errors = np.mean(np.square(X - reconstructions), axis=1)
        return errors
    
    def detect_anomalies(
        self,
        X: np.ndarray,
        return_scores: bool = True
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """
        Detect anomalies in the input data.
        
        Args:
            X: Input data
            return_scores: Whether to return anomaly scores
            
        Returns:
            Boolean array of anomaly flags, optionally with scores
        """
        if self.threshold is None:
            raise ValueError("Model must be trained before detecting anomalies")
        
        errors = self.get_reconstruction_error(X)
        is_anomaly = errors > self.threshold
        
        if return_scores:
            return is_anomaly, errors
        return is_anomaly
    
    def get_risk_level(self, error: float) -> str:
        """
        Map reconstruction error to LOW/MEDIUM/HIGH/CRITICAL **relative to the
        anomaly threshold**, not raw training percentiles.

        Using percentiles (p50/p75/p95) of training errors was misleading: the
        decision threshold is typically mean + k·σ (~top ~1%), which is *above*
        the 95th percentile of training errors. So any ``error > threshold``
        (anomaly) was almost always above p95 → always CRITICAL.

        Args:
            error: Reconstruction error (MSE)

        Returns:
            Risk level string: 'LOW', 'MEDIUM', 'HIGH', or 'CRITICAL'
        """
        if self.threshold is None:
            return 'LOW'
        if error <= self.threshold:
            return 'LOW'
        ratio = error / (float(self.threshold) + 1e-12)
        # Mildly above threshold → MEDIUM; stronger → HIGH; extreme → CRITICAL
        if ratio <= 1.15:
            return 'MEDIUM'
        if ratio <= 1.40:
            return 'HIGH'
        return 'CRITICAL'
    
    def get_feature_importance(
        self,
        X: np.ndarray,
        feature_names: List[str]
    ) -> Dict[str, float]:
        """
        Calculate feature importance based on reconstruction error contribution.
        
        Args:
            X: Input sample(s)
            feature_names: List of feature names
            
        Returns:
            Dictionary of feature name to importance score
        """
        reconstructions = self.predict(X)
        
        # Per-feature squared error
        feature_errors = np.mean(np.square(X - reconstructions), axis=0)
        
        # Normalize to sum to 1
        total_error = np.sum(feature_errors)
        if total_error > 0:
            importance = feature_errors / total_error
        else:
            importance = np.zeros_like(feature_errors)
        
        return dict(zip(feature_names, importance))
    
    def get_latent_representation(self, X: np.ndarray) -> np.ndarray:
        """
        Get latent space representation of input data.
        
        Useful for visualization and clustering.
        
        Args:
            X: Input data
            
        Returns:
            Latent space representations
        """
        return self.encoder.predict(X, verbose=0)
    
    def save(self, path: Union[str, Path]) -> None:
        """
        Save model and metadata.
        
        Args:
            path: Directory path to save model
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        # Save Keras model
        self.model.save(path / 'autoencoder.keras')
        self.encoder.save(path / 'encoder.keras')
        self.decoder.save(path / 'decoder.keras')
        
        # Save metadata
        metadata = {
            'input_dim': self.input_dim,
            'encoding_dim': self.encoding_dim,
            'hidden_layers': self.hidden_layers,
            'dropout_rate': self.dropout_rate,
            'learning_rate': self.learning_rate,
            'l2_regularization': self.l2_regularization,
            'threshold': float(self.threshold) if self.threshold else None,
            'mean_error': float(self.mean_error) if self.mean_error else None,
            'std_error': float(self.std_error) if self.std_error else None,
            'error_percentiles': {str(k): float(v) for k, v in self.error_percentiles.items()} if hasattr(self, 'error_percentiles') else None,
            'history': self.history
        }
        
        with open(path / 'metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"Model saved to {path}")
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> 'WeatherAutoencoder':
        """
        Load model from disk.
        
        Args:
            path: Directory path containing saved model
            
        Returns:
            Loaded WeatherAutoencoder instance
        """
        path = Path(path)
        
        # Load metadata
        with open(path / 'metadata.json', 'r') as f:
            metadata = json.load(f)
        
        # Create instance
        instance = cls(
            input_dim=metadata['input_dim'],
            encoding_dim=metadata['encoding_dim'],
            hidden_layers=metadata['hidden_layers'],
            dropout_rate=metadata['dropout_rate'],
            learning_rate=metadata['learning_rate'],
            l2_regularization=metadata['l2_regularization']
        )
        
        # Load Keras models
        instance.model = keras.models.load_model(path / 'autoencoder.keras')
        instance.encoder = keras.models.load_model(path / 'encoder.keras')
        instance.decoder = keras.models.load_model(path / 'decoder.keras')
        
        # Restore metadata
        instance.threshold = metadata['threshold']
        instance.mean_error = metadata['mean_error']
        instance.std_error = metadata['std_error']
        instance.history = metadata['history']
        
        if metadata['error_percentiles']:
            instance.error_percentiles = {int(k): v for k, v in metadata['error_percentiles'].items()}
        
        logger.info(f"Model loaded from {path}")
        return instance


class LSTMAutoencoder:
    """
    LSTM Autoencoder for temporal pattern learning in weather data.
    
    This model captures sequential dependencies in weather patterns,
    making it especially effective for detecting anomalies that involve
    unusual temporal sequences (e.g., sudden weather changes).
    """
    
    def __init__(
        self,
        sequence_length: int,
        n_features: int,
        lstm_units: int = 32,
        encoding_dim: int = 8,
        dropout_rate: float = 0.2,
        learning_rate: float = 0.001
    ):
        """
        Initialize LSTM Autoencoder.
        
        Args:
            sequence_length: Number of time steps in each sequence
            n_features: Number of features per time step
            lstm_units: Number of LSTM units
            encoding_dim: Dimension of latent space
            dropout_rate: Dropout rate
            learning_rate: Learning rate
        """
        self.sequence_length = sequence_length
        self.n_features = n_features
        self.lstm_units = lstm_units
        self.encoding_dim = encoding_dim
        self.dropout_rate = dropout_rate
        self.learning_rate = learning_rate
        
        self.model: Optional[Model] = None
        self.encoder: Optional[Model] = None
        self.history: Optional[dict] = None
        self.threshold: Optional[float] = None
        self.mean_error: Optional[float] = None
        self.std_error: Optional[float] = None
        
        self._build_model()
    
    def _build_model(self) -> None:
        """Build the LSTM Autoencoder architecture."""
        logger.info(f"Building LSTM Autoencoder: seq_len={self.sequence_length}, "
                   f"features={self.n_features}, lstm_units={self.lstm_units}")
        
        # === ENCODER ===
        encoder_input = layers.Input(shape=(self.sequence_length, self.n_features), name='encoder_input')
        
        # LSTM layers
        x = layers.LSTM(self.lstm_units, activation='tanh', return_sequences=True, name='encoder_lstm_1')(encoder_input)
        x = layers.Dropout(self.dropout_rate)(x)
        x = layers.LSTM(self.lstm_units // 2, activation='tanh', return_sequences=False, name='encoder_lstm_2')(x)
        x = layers.Dropout(self.dropout_rate)(x)
        
        # Latent representation
        latent = layers.Dense(self.encoding_dim, activation='relu', name='latent')(x)
        
        self.encoder = Model(encoder_input, latent, name='encoder')
        
        # === DECODER ===
        x = layers.RepeatVector(self.sequence_length, name='repeat')(latent)
        x = layers.LSTM(self.lstm_units // 2, activation='tanh', return_sequences=True, name='decoder_lstm_1')(x)
        x = layers.Dropout(self.dropout_rate)(x)
        x = layers.LSTM(self.lstm_units, activation='tanh', return_sequences=True, name='decoder_lstm_2')(x)
        x = layers.Dropout(self.dropout_rate)(x)
        
        decoder_output = layers.TimeDistributed(
            layers.Dense(self.n_features), 
            name='decoder_output'
        )(x)
        
        # Full model
        self.model = Model(encoder_input, decoder_output, name='lstm_autoencoder')
        
        optimizer = keras.optimizers.Adam(learning_rate=self.learning_rate)
        self.model.compile(optimizer=optimizer, loss='mse', metrics=['mae'])
        
        logger.info("LSTM Autoencoder model built successfully")
        self.model.summary(print_fn=logger.info)
    
    def train(
        self,
        X_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        epochs: int = 100,
        batch_size: int = 32,
        early_stopping_patience: int = 10,
        threshold_k: float = 3.0
    ) -> Dict:
        """Train the LSTM Autoencoder."""
        logger.info(f"Starting LSTM training: epochs={epochs}, batch_size={batch_size}")
        
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=early_stopping_patience,
                restore_best_weights=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=1e-6,
                verbose=1
            )
        ]
        
        if X_val is None:
            split_idx = int(len(X_train) * 0.8)
            X_val = X_train[split_idx:]
            X_train = X_train[:split_idx]
        
        history = self.model.fit(
            X_train, X_train,
            validation_data=(X_val, X_val),
            epochs=epochs,
            batch_size=batch_size,
            callbacks=callbacks,
            verbose=1
        )
        
        self.history = history.history
        self._calculate_threshold(X_train, threshold_k)
        
        return self.history
    
    def _calculate_threshold(self, X: np.ndarray, k: float = 3.0) -> None:
        """Calculate anomaly threshold for LSTM model."""
        reconstructions = self.model.predict(X, verbose=0)
        # MSE across all time steps and features
        errors = np.mean(np.square(X - reconstructions), axis=(1, 2))
        
        self.mean_error = np.mean(errors)
        self.std_error = np.std(errors)
        self.threshold = self.mean_error + k * self.std_error
        
        self.error_percentiles = {
            50: np.percentile(errors, 50),
            75: np.percentile(errors, 75),
            90: np.percentile(errors, 90),
            95: np.percentile(errors, 95),
            99: np.percentile(errors, 99)
        }
    
    def get_reconstruction_error(self, X: np.ndarray) -> np.ndarray:
        """Calculate reconstruction error for sequences."""
        reconstructions = self.model.predict(X, verbose=0)
        errors = np.mean(np.square(X - reconstructions), axis=(1, 2))
        return errors
    
    def detect_anomalies(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Detect anomalies in sequence data."""
        errors = self.get_reconstruction_error(X)
        is_anomaly = errors > self.threshold
        return is_anomaly, errors
    
    def save(self, path: Union[str, Path]) -> None:
        """Save LSTM model and metadata."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        self.model.save(path / 'lstm_autoencoder.keras')
        self.encoder.save(path / 'lstm_encoder.keras')
        
        metadata = {
            'sequence_length': self.sequence_length,
            'n_features': self.n_features,
            'lstm_units': self.lstm_units,
            'encoding_dim': self.encoding_dim,
            'dropout_rate': self.dropout_rate,
            'learning_rate': self.learning_rate,
            'threshold': float(self.threshold) if self.threshold else None,
            'mean_error': float(self.mean_error) if self.mean_error else None,
            'std_error': float(self.std_error) if self.std_error else None,
            'error_percentiles': {str(k): float(v) for k, v in self.error_percentiles.items()} if hasattr(self, 'error_percentiles') else None
        }
        
        with open(path / 'lstm_metadata.json', 'w') as f:
            json.dump(metadata, f, indent=2)
        
        logger.info(f"LSTM model saved to {path}")
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> 'LSTMAutoencoder':
        """Load LSTM model from disk."""
        path = Path(path)
        
        with open(path / 'lstm_metadata.json', 'r') as f:
            metadata = json.load(f)
        
        instance = cls(
            sequence_length=metadata['sequence_length'],
            n_features=metadata['n_features'],
            lstm_units=metadata['lstm_units'],
            encoding_dim=metadata['encoding_dim'],
            dropout_rate=metadata['dropout_rate'],
            learning_rate=metadata['learning_rate']
        )
        
        instance.model = keras.models.load_model(path / 'lstm_autoencoder.keras')
        instance.encoder = keras.models.load_model(path / 'lstm_encoder.keras')
        instance.threshold = metadata['threshold']
        instance.mean_error = metadata['mean_error']
        instance.std_error = metadata['std_error']
        
        if metadata['error_percentiles']:
            instance.error_percentiles = {int(k): v for k, v in metadata['error_percentiles'].items()}
        
        return instance


class HybridAnomalyDetector:
    """
    Hybrid Anomaly Detector combining Autoencoder and LSTM-Autoencoder.
    
    This model leverages both:
    - Point-wise anomaly detection (Autoencoder)
    - Sequential pattern anomaly detection (LSTM-Autoencoder)
    
    Final anomaly score is a weighted combination of both models.
    """
    
    def __init__(
        self,
        autoencoder: WeatherAutoencoder,
        lstm_autoencoder: Optional[LSTMAutoencoder] = None,
        weight_ae: float = 0.6,
        weight_lstm: float = 0.4
    ):
        """
        Initialize Hybrid Detector.
        
        Args:
            autoencoder: Trained WeatherAutoencoder
            lstm_autoencoder: Trained LSTMAutoencoder (optional)
            weight_ae: Weight for autoencoder score
            weight_lstm: Weight for LSTM score
        """
        self.autoencoder = autoencoder
        self.lstm_autoencoder = lstm_autoencoder
        self.weight_ae = weight_ae
        self.weight_lstm = weight_lstm
        
        # If no LSTM, use only autoencoder
        if lstm_autoencoder is None:
            self.weight_ae = 1.0
            self.weight_lstm = 0.0
    
    def detect_anomalies(
        self,
        X_point: np.ndarray,
        X_sequence: Optional[np.ndarray] = None
    ) -> Dict:
        """
        Detect anomalies using hybrid approach.
        
        Args:
            X_point: Point-wise features for autoencoder
            X_sequence: Sequence features for LSTM (optional)
            
        Returns:
            Dictionary with anomaly results
        """
        results = {
            'ae_score': None,
            'lstm_score': None,
            'combined_score': None,
            'is_anomaly': None
        }
        
        # Autoencoder detection
        ae_is_anomaly, ae_errors = self.autoencoder.detect_anomalies(X_point)
        # Normalize errors to [0, 1] range
        ae_scores = (ae_errors - self.autoencoder.mean_error) / (self.autoencoder.std_error + 1e-8)
        ae_scores = np.clip(ae_scores / 5, 0, 1)  # Clip to reasonable range
        results['ae_score'] = ae_scores
        
        # LSTM detection (if available)
        if self.lstm_autoencoder is not None and X_sequence is not None:
            lstm_is_anomaly, lstm_errors = self.lstm_autoencoder.detect_anomalies(X_sequence)
            lstm_scores = (lstm_errors - self.lstm_autoencoder.mean_error) / (self.lstm_autoencoder.std_error + 1e-8)
            lstm_scores = np.clip(lstm_scores / 5, 0, 1)
            results['lstm_score'] = lstm_scores
            
            # Combined score
            combined = self.weight_ae * ae_scores + self.weight_lstm * lstm_scores
        else:
            combined = ae_scores
        
        results['combined_score'] = combined
        results['is_anomaly'] = combined > 0.5  # Normalized threshold
        
        return results
