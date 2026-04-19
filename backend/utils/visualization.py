"""
Visualization Utilities for Anomaly Detection Analysis
======================================================
This module provides visualization functions for:
- Training loss curves
- Anomaly distribution plots
- Feature importance visualization
- Reconstruction error analysis
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)

# Set style
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_palette("husl")


def plot_training_history(
    history: Dict[str, List[float]],
    save_path: Optional[str] = None,
    title: str = "Model Training History"
) -> plt.Figure:
    """
    Plot training and validation loss curves.
    
    Args:
        history: Training history dictionary with 'loss' and 'val_loss' keys
        save_path: Optional path to save the figure
        title: Plot title
        
    Returns:
        Matplotlib figure object
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    epochs = range(1, len(history['loss']) + 1)
    
    # Loss plot
    axes[0].plot(epochs, history['loss'], 'b-', label='Training Loss', linewidth=2)
    axes[0].plot(epochs, history['val_loss'], 'r--', label='Validation Loss', linewidth=2)
    axes[0].set_xlabel('Epoch', fontsize=12)
    axes[0].set_ylabel('Loss (MSE)', fontsize=12)
    axes[0].set_title('Training vs Validation Loss', fontsize=14)
    axes[0].legend(fontsize=10)
    axes[0].grid(True, alpha=0.3)
    
    # MAE plot if available
    if 'mae' in history:
        axes[1].plot(epochs, history['mae'], 'b-', label='Training MAE', linewidth=2)
        axes[1].plot(epochs, history['val_mae'], 'r--', label='Validation MAE', linewidth=2)
        axes[1].set_xlabel('Epoch', fontsize=12)
        axes[1].set_ylabel('MAE', fontsize=12)
        axes[1].set_title('Training vs Validation MAE', fontsize=14)
        axes[1].legend(fontsize=10)
        axes[1].grid(True, alpha=0.3)
    else:
        # Log scale loss
        axes[1].semilogy(epochs, history['loss'], 'b-', label='Training Loss', linewidth=2)
        axes[1].semilogy(epochs, history['val_loss'], 'r--', label='Validation Loss', linewidth=2)
        axes[1].set_xlabel('Epoch', fontsize=12)
        axes[1].set_ylabel('Loss (Log Scale)', fontsize=12)
        axes[1].set_title('Loss (Log Scale)', fontsize=14)
        axes[1].legend(fontsize=10)
        axes[1].grid(True, alpha=0.3)
    
    fig.suptitle(title, fontsize=16, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Training history plot saved to {save_path}")
    
    return fig


def plot_reconstruction_error_distribution(
    errors: np.ndarray,
    threshold: float,
    save_path: Optional[str] = None,
    title: str = "Reconstruction Error Distribution"
) -> plt.Figure:
    """
    Plot the distribution of reconstruction errors with anomaly threshold.
    
    Args:
        errors: Array of reconstruction errors
        threshold: Anomaly detection threshold
        save_path: Optional path to save the figure
        title: Plot title
        
    Returns:
        Matplotlib figure object
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Histogram
    n_bins = min(100, len(errors) // 20)
    axes[0].hist(errors, bins=n_bins, density=True, alpha=0.7, 
                 color='steelblue', edgecolor='black', linewidth=0.5)
    axes[0].axvline(threshold, color='red', linestyle='--', linewidth=2, 
                    label=f'Threshold: {threshold:.4f}')
    axes[0].set_xlabel('Reconstruction Error', fontsize=12)
    axes[0].set_ylabel('Density', fontsize=12)
    axes[0].set_title('Error Distribution (Histogram)', fontsize=14)
    axes[0].legend(fontsize=10)
    axes[0].grid(True, alpha=0.3)
    
    # Add annotations
    normal_pct = np.mean(errors <= threshold) * 100
    anomaly_pct = np.mean(errors > threshold) * 100
    axes[0].annotate(f'Normal: {normal_pct:.1f}%', 
                     xy=(0.05, 0.95), xycoords='axes fraction',
                     fontsize=10, va='top',
                     bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))
    axes[0].annotate(f'Anomaly: {anomaly_pct:.1f}%', 
                     xy=(0.05, 0.85), xycoords='axes fraction',
                     fontsize=10, va='top',
                     bbox=dict(boxstyle='round', facecolor='lightcoral', alpha=0.5))
    
    # Box plot
    is_anomaly = errors > threshold
    data = [errors[~is_anomaly], errors[is_anomaly]]
    bp = axes[1].boxplot(data, labels=['Normal', 'Anomaly'], patch_artist=True)
    bp['boxes'][0].set_facecolor('lightgreen')
    bp['boxes'][1].set_facecolor('lightcoral')
    axes[1].set_ylabel('Reconstruction Error', fontsize=12)
    axes[1].set_title('Error Distribution by Class', fontsize=14)
    axes[1].grid(True, alpha=0.3)
    
    fig.suptitle(title, fontsize=16, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Error distribution plot saved to {save_path}")
    
    return fig


def plot_anomalies_over_time(
    df: pd.DataFrame,
    errors: np.ndarray,
    threshold: float,
    date_column: str = 'date',
    save_path: Optional[str] = None
) -> plt.Figure:
    """
    Plot anomalies over time.
    
    Args:
        df: DataFrame with date information
        errors: Reconstruction errors
        threshold: Anomaly threshold
        date_column: Name of date column
        save_path: Optional path to save figure
        
    Returns:
        Matplotlib figure object
    """
    fig, axes = plt.subplots(2, 1, figsize=(16, 10), sharex=True)
    
    dates = pd.to_datetime(df[date_column])
    is_anomaly = errors > threshold
    
    # Error over time
    axes[0].scatter(dates[~is_anomaly], errors[~is_anomaly], 
                   alpha=0.3, s=10, c='steelblue', label='Normal')
    axes[0].scatter(dates[is_anomaly], errors[is_anomaly], 
                   alpha=0.7, s=30, c='red', marker='x', label='Anomaly')
    axes[0].axhline(threshold, color='red', linestyle='--', linewidth=1.5, 
                    label=f'Threshold: {threshold:.4f}')
    axes[0].set_ylabel('Reconstruction Error', fontsize=12)
    axes[0].set_title('Reconstruction Error Over Time', fontsize=14)
    axes[0].legend(loc='upper right', fontsize=10)
    axes[0].grid(True, alpha=0.3)
    
    # Anomaly count by month
    df_temp = df.copy()
    df_temp['error'] = errors
    df_temp['is_anomaly'] = is_anomaly
    df_temp['year_month'] = df_temp[date_column].dt.to_period('M')
    
    monthly_counts = df_temp.groupby('year_month')['is_anomaly'].sum()
    monthly_counts.plot(kind='bar', ax=axes[1], color='coral', alpha=0.7)
    axes[1].set_xlabel('Month', fontsize=12)
    axes[1].set_ylabel('Anomaly Count', fontsize=12)
    axes[1].set_title('Monthly Anomaly Count', fontsize=14)
    axes[1].tick_params(axis='x', rotation=45)
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Anomalies over time plot saved to {save_path}")
    
    return fig


def plot_feature_importance(
    feature_importance: Dict[str, float],
    top_n: int = 10,
    save_path: Optional[str] = None,
    title: str = "Feature Importance for Anomaly Detection"
) -> plt.Figure:
    """
    Plot feature importance based on reconstruction error contribution.
    
    Args:
        feature_importance: Dictionary of feature name to importance score
        top_n: Number of top features to display
        save_path: Optional path to save figure
        title: Plot title
        
    Returns:
        Matplotlib figure object
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Sort and get top features
    sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:top_n]
    features = [f[0] for f in sorted_features]
    importances = [f[1] for f in sorted_features]
    
    colors = plt.cm.viridis(np.linspace(0.2, 0.8, len(features)))
    
    bars = ax.barh(features, importances, color=colors, edgecolor='black', linewidth=0.5)
    
    # Add value labels
    for bar, imp in zip(bars, importances):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                f'{imp:.3f}', va='center', fontsize=10)
    
    ax.set_xlabel('Importance Score', fontsize=12)
    ax.set_ylabel('Feature', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Feature importance plot saved to {save_path}")
    
    return fig


def plot_anomaly_heatmap(
    df: pd.DataFrame,
    errors: np.ndarray,
    threshold: float,
    group_cols: Tuple[str, str] = ('city', 'month'),
    save_path: Optional[str] = None
) -> plt.Figure:
    """
    Plot heatmap of anomaly frequency by two grouping variables.
    
    Args:
        df: DataFrame with grouping columns
        errors: Reconstruction errors
        threshold: Anomaly threshold
        group_cols: Tuple of column names to group by
        save_path: Optional path to save figure
        
    Returns:
        Matplotlib figure object
    """
    fig, ax = plt.subplots(figsize=(12, 8))
    
    df_temp = df.copy()
    df_temp['is_anomaly'] = errors > threshold
    
    # Pivot for heatmap
    pivot_table = df_temp.pivot_table(
        values='is_anomaly',
        index=group_cols[0],
        columns=group_cols[1],
        aggfunc='sum'
    )
    
    sns.heatmap(pivot_table, annot=True, fmt='g', cmap='YlOrRd',
                linewidths=0.5, ax=ax)
    
    ax.set_title(f'Anomaly Count by {group_cols[0].title()} and {group_cols[1].title()}',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel(group_cols[1].title(), fontsize=12)
    ax.set_ylabel(group_cols[0].title(), fontsize=12)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Anomaly heatmap saved to {save_path}")
    
    return fig


def plot_latent_space(
    latent_vectors: np.ndarray,
    labels: np.ndarray,
    save_path: Optional[str] = None,
    title: str = "Latent Space Visualization"
) -> plt.Figure:
    """
    Plot 2D visualization of latent space using first 2 dimensions.
    
    Args:
        latent_vectors: Latent space representations
        labels: Binary labels (0=normal, 1=anomaly)
        save_path: Optional path to save figure
        title: Plot title
        
    Returns:
        Matplotlib figure object
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Use first 2 dimensions
    if latent_vectors.shape[1] >= 2:
        x = latent_vectors[:, 0]
        y = latent_vectors[:, 1]
    else:
        x = latent_vectors[:, 0]
        y = np.zeros_like(x)
    
    # Plot normal points
    normal_mask = labels == 0
    ax.scatter(x[normal_mask], y[normal_mask], 
               c='steelblue', alpha=0.5, s=20, label='Normal')
    
    # Plot anomalies
    anomaly_mask = labels == 1
    ax.scatter(x[anomaly_mask], y[anomaly_mask], 
               c='red', alpha=0.8, s=50, marker='x', label='Anomaly')
    
    ax.set_xlabel('Latent Dimension 1', fontsize=12)
    ax.set_ylabel('Latent Dimension 2', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        logger.info(f"Latent space plot saved to {save_path}")
    
    return fig


def create_analysis_report(
    output_dir: str,
    history: Dict,
    errors: np.ndarray,
    threshold: float,
    df: pd.DataFrame,
    feature_importance: Dict[str, float]
) -> None:
    """
    Generate complete visual analysis report.
    
    Args:
        output_dir: Directory to save visualizations
        history: Training history
        errors: Reconstruction errors
        threshold: Anomaly threshold
        df: Original DataFrame
        feature_importance: Feature importance scores
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Generating analysis report in {output_dir}")
    
    # Generate all plots
    plot_training_history(history, save_path=str(output_path / 'training_history.png'))
    plot_reconstruction_error_distribution(errors, threshold, 
                                          save_path=str(output_path / 'error_distribution.png'))
    
    if 'date' in df.columns:
        plot_anomalies_over_time(df, errors, threshold, 
                                save_path=str(output_path / 'anomalies_timeline.png'))
    
    plot_feature_importance(feature_importance, 
                           save_path=str(output_path / 'feature_importance.png'))
    
    if 'city' in df.columns and 'month' in df.columns:
        plot_anomaly_heatmap(df, errors, threshold, 
                            save_path=str(output_path / 'anomaly_heatmap.png'))
    
    logger.info("Analysis report generation complete")
    plt.close('all')
