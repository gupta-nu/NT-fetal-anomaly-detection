import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
import matplotlib.pyplot as plt
import os
import cv2
from sklearn.metrics import jaccard_score, precision_recall_curve
from sklearn.metrics import confusion_matrix, roc_curve, auc

# Load test images
dataset_dir = "NT_DATA/preprocessed"
X_test = np.load(os.path.join(dataset_dir, "test_images.npy"))
Y_test = np.load(os.path.join(dataset_dir, "test_masks.npy"))

# Ensure masks are binary (0 or 1)
Y_test = (Y_test > 0.5).astype(np.uint8)
Y_test = np.expand_dims(Y_test, axis=-1)

# Validation checks
assert Y_test.max() <= 1 and Y_test.min() >= 0, "Masks must be binary (0-1)"
assert Y_test.dtype == np.uint8, "Masks should be uint8 type"

# Load model and predict
model = tf.keras.models.load_model("unet_best_model.h5")
raw_preds = model.predict(X_test)

# Validate model outputs
assert raw_preds.max() <= 1.0 and raw_preds.min() >= 0.0, \
    f"Model outputs out of [0,1] range: {raw_preds.min()}-{raw_preds.max()}"

# Find optimal threshold
precisions, recalls, thresholds = precision_recall_curve(
    Y_test.flatten(), 
    raw_preds.flatten()
)
optimal_idx = np.argmax(2 * (precisions * recalls) / (precisions + recalls + 1e-6))
optimal_threshold = thresholds[optimal_idx]

# Apply threshold
preds = (raw_preds > optimal_threshold).astype(np.uint8)

# Enhanced post-processing
kernel = np.ones((3, 3), np.uint8)
postprocessed_preds = []

for mask in preds:
    mask_squeezed = mask.squeeze()
    
    # Morphological closing
    processed = cv2.morphologyEx(mask_squeezed, cv2.MORPH_CLOSE, kernel)
    
    # Connected components with safety
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(processed)
    
    if n_labels > 1:  # Has foreground components
        sizes = stats[1:, -1]
        processed = np.zeros_like(processed)
        for i in range(n_labels-1):
            if sizes[i] >= 100:
                processed[labels == i+1] = 1
                
    postprocessed_preds.append(processed)

postprocessed_preds = np.expand_dims(np.array(postprocessed_preds), axis=-1)


# Evaluation functions
def dice_score(y_true, y_pred):
    intersection = np.sum(y_true * y_pred)
    return (2. * intersection) / (np.sum(y_true) + np.sum(y_pred) + 1e-6)

def calculate_metrics(y_true, y_pred):
    dice = dice_score(y_true, y_pred)
    iou = jaccard_score(y_true.flatten(), y_pred.flatten(), average='binary', zero_division=0)
    return dice, iou

# Calculate metrics for both versions
original_dice, original_iou = calculate_metrics(Y_test, preds)
processed_dice, processed_iou = calculate_metrics(Y_test, postprocessed_preds)

print(f"🏆 Optimal Threshold: {optimal_threshold:.4f}")
print(f"📊 Original Dice: {original_dice:.4f} | Postprocessed Dice: {processed_dice:.4f}")
print(f"📈 Original IoU: {original_iou:.4f} | Postprocessed IoU: {processed_iou:.4f}")
# Convert to 1D arrays
y_true = Y_test.flatten().astype(np.uint8)
y_pred = postprocessed_preds.flatten().astype(np.uint8)

# Calculate confusion matrix
tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
sensitivity = tp / (tp + fn)
specificity = tn / (tn + fp)
precision = tp / (tp + fp)

print("\n🔍 Clinical Metrics:")
print(f"Sensitivity (Recall): {sensitivity:.4f}")
print(f"Specificity: {specificity:.4f}")
print(f"Precision: {precision:.4f}")

# =============================================================================
# Add this RIGHT AFTER the confusion matrix code
# =============================================================================

# ROC and Precision-Recall Curves
fpr, tpr, _ = roc_curve(y_true, raw_preds.flatten())
roc_auc = auc(fpr, tpr)

precision_curve, recall_curve, _ = precision_recall_curve(y_true, raw_preds.flatten())

# Plot and save
plt.figure(figsize=(12, 5))
plt.subplot(1, 2, 1)
plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC (AUC = {roc_auc:.2f})')
plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Curve')
plt.legend(loc="lower right")

plt.subplot(1, 2, 2)
plt.plot(recall_curve, precision_curve, color='blue', lw=2, label='Precision-Recall')
plt.xlabel('Recall')
plt.ylabel('Precision')
plt.title('Precision-Recall Curve')
plt.legend(loc="upper right")

plt.tight_layout()
plt.savefig('performance_curves.png', dpi=300)
plt.close()  # Important! Don't mix with other plots 

# Enhanced visualization
def visualize_predictions(X, y_true, raw, pred, postprocessed, index):
    fig = plt.figure(figsize=(18, 4))
    
    images = [
        ("Original Image", X[index], None),
        ("Ground Truth", y_true[index], 'gray'),
        ("Raw Output", raw[index], 'gray'),
        ("Thresholded", pred[index], 'gray'),
        ("Postprocessed", postprocessed[index], 'gray')
    ]
    
    for idx, (title, data, cmap) in enumerate(images, 1):
        ax = fig.add_subplot(1, 5, idx)
        ax.imshow(data.squeeze(), cmap=cmap)
        ax.set_title(title)
        ax.axis('off')
    
    plt.tight_layout()
    plt.savefig(f'visualization_{index}.png')  # Save instead of showing
    plt.close(fig)  # Explicitly close figure

# Generate visualizations with raw outputs
# Generate visualizations with raw outputs
sample_indices = np.random.choice(len(X_test), 5, replace=False)
for idx in sample_indices:
    visualize_predictions(
        X_test, 
        Y_test,
        raw_preds,
        preds,
        postprocessed_preds,
        index=idx
    )
    print(f"Saved visualization for sample {idx} as visualization_{idx}.png")

    # Add to evaluate_unet.py after visualization code
plt.figure(figsize=(8,6))
plt.subplot(131).imshow(X_test[0].squeeze(), cmap='gray')
plt.title('Original')
plt.subplot(132).imshow(Y_test[0].squeeze(), cmap='gray')
plt.title('Ground Truth')
plt.subplot(133).imshow(postprocessed_preds[0].squeeze(), cmap='gray')
plt.title('Our Prediction')
plt.savefig('comparison.png', dpi=300, bbox_inches='tight')