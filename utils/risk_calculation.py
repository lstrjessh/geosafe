"""
Risk calculation functions for GeoSafe Landslide Risk Mapper
"""

import ee
import streamlit as st

def calculate_risk_score(recent_image, historical_image, roi, veg_weight, moisture_weight, slope_weight, veg_threshold, water_threshold):
    """Calculate composite risk score"""
    
    # Extract NDVI and NDWI bands
    recent_ndvi = recent_image.select('NDVI')
    historical_ndvi = historical_image.select('NDVI')
    recent_ndwi = recent_image.select('NDWI')
    historical_ndwi = historical_image.select('NDWI')
    
    # Create vegetation and water masks
    vegetation_mask_recent = recent_ndvi.gt(veg_threshold)
    vegetation_mask_historical = historical_ndvi.gt(veg_threshold)
    vegetation_mask_both = vegetation_mask_recent.And(vegetation_mask_historical)
    
    water_mask_recent = recent_ndwi.gt(water_threshold)
    water_mask_historical = historical_ndwi.gt(water_threshold)
    water_mask_combined = water_mask_recent.Or(water_mask_historical)
    
    # Get slope data
    slope = ee.Algorithms.Terrain(ee.Image('USGS/SRTMGL1_003').clip(roi)).select('slope')
    
    # Calculate vegetation loss
    veg_loss = historical_ndvi.subtract(recent_ndvi).rename('VEG_LOSS')
    veg_loss_norm = veg_loss.max(0).unitScale(0, 0.4).clamp(0, 1)
    
    # Normalize moisture and slope
    moisture_norm = recent_ndwi.max(0).unitScale(0, 0.6).clamp(0, 1)
    slope_norm = slope.unitScale(5, 45).clamp(0, 1)
    
    # Calculate composite risk score
    risk_score = (
        veg_loss_norm.multiply(veg_weight)
        .add(moisture_norm.multiply(moisture_weight))
        .add(slope_norm.multiply(slope_weight))
    ).rename('RISK_SCORE')
    
    # Apply masks
    risk_score_masked = risk_score.updateMask(vegetation_mask_both.And(water_mask_combined.Not()))
    
    # Calculate risk threshold
    percentile_dict = risk_score_masked.reduceRegion(
        reducer=ee.Reducer.percentile([85, 90]),
        geometry=roi,
        scale=30,
        maxPixels=1e9,
        bestEffort=True,
        tileScale=2,
    )
    
    p90 = ee.Number(percentile_dict.get('RISK_SCORE_p90'))
    p85 = ee.Number(percentile_dict.get('RISK_SCORE_p85'))
    risk_threshold = ee.Number(ee.Algorithms.If(p90, p90, p85))
    risk_threshold = ee.Number(ee.Algorithms.If(risk_threshold, risk_threshold, 0.45))
    
    # Create risk hotspots
    risk_hotspots = risk_score_masked.gte(risk_threshold).selfMask().rename('RISK_HOTSPOTS')
    
    # Get threshold value
    try:
        risk_threshold_value = risk_threshold.getInfo()
    except Exception:
        risk_threshold_value = 0.45
    
    # Calculate high-risk percentage
    try:
        high_risk_stats = risk_hotspots.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi,
            scale=30,
            maxPixels=1e9,
            bestEffort=True
        )
        total_pixels = risk_score_masked.reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=roi,
            scale=30,
            maxPixels=1e9,
            bestEffort=True
        )
        
        high_risk_pixels = high_risk_stats.get('RISK_HOTSPOTS', 0).getInfo() or 0
        total_pixel_count = total_pixels.get('RISK_SCORE', 0).getInfo() or 1
        high_risk_percentage = (high_risk_pixels / total_pixel_count) * 100
    except Exception:
        high_risk_percentage = 0
    
    return {
        'risk_score': risk_score_masked,
        'risk_hotspots': risk_hotspots,
        'risk_threshold': risk_threshold_value,
        'high_risk_percentage': high_risk_percentage,
        'vegetation_mask': vegetation_mask_both,
        'water_mask': water_mask_combined,
        'slope': slope,
        'veg_loss': veg_loss_norm,
        'moisture': moisture_norm
    }

def calculate_ndvi_change(recent_image, historical_image, roi, veg_threshold, water_threshold, loss_threshold):
    """Calculate NDVI change and generate alerts"""
    
    # Extract NDVI bands
    recent_ndvi = recent_image.select('NDVI')
    historical_ndvi = historical_image.select('NDVI')
    recent_ndwi = recent_image.select('NDWI')
    historical_ndwi = historical_image.select('NDWI')
    
    # Create masks
    vegetation_mask_recent = recent_ndvi.gt(veg_threshold)
    vegetation_mask_historical = historical_ndvi.gt(veg_threshold)
    vegetation_mask_both = vegetation_mask_recent.And(vegetation_mask_historical)
    
    water_mask_recent = recent_ndwi.gt(water_threshold)
    water_mask_historical = historical_ndwi.gt(water_threshold)
    water_mask_combined = water_mask_recent.Or(water_mask_historical)
    
    # Calculate NDVI difference
    ndvi_difference = recent_ndvi.subtract(historical_ndvi)
    ndvi_difference_masked = ndvi_difference.updateMask(vegetation_mask_both.And(water_mask_combined.Not()))
    
    # Calculate mean NDVI change
    mean_ndvi_change_dict = ndvi_difference_masked.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=30,
    )
    
    mean_ndvi_change_value = None
    mean_ndvi_change = mean_ndvi_change_dict.get('NDVI')
    if mean_ndvi_change is not None:
        try:
            mean_ndvi_change_value = mean_ndvi_change.getInfo()
        except Exception:
            pass
    
    # Generate alert message
    if mean_ndvi_change_value is None:
        alert_message = (
            '>>> DATA WARNING: Unable to compute NDVI change for the selected period.\n'
            '>>> Please verify imagery availability or adjust the ROI and time range.\n'
        )
        alert_type = 'warning'
        risk_level = 'Unknown'
    else:
        ndvi_change_percent = (mean_ndvi_change_value / abs(mean_ndvi_change_value + 1)) * 100 if mean_ndvi_change_value != 0 else 0
        
        if mean_ndvi_change_value < loss_threshold:
            alert_message = (
                '>>> RISK DETECTED: Significant vegetation loss identified.\n'
                '>>> This area is flagged as a high-risk hotspot.\n'
                '>>> Recommendation: Deploy Geo-Safe Sensor Nodes to this location.'
            )
            alert_type = 'danger'
            risk_level = 'High'
        else:
            alert_message = (
                '>>> MONITORING: No significant large-scale vegetation loss detected.\n'
                '>>> Continue routine satellite monitoring of this area.'
            )
            alert_type = 'success'
            risk_level = 'Low'
    
    return {
        'ndvi_change': ndvi_difference_masked,
        'mean_ndvi_change': mean_ndvi_change_value or 0,
        'ndvi_change_percent': ndvi_change_percent,
        'alert_message': alert_message,
        'alert_type': alert_type,
        'risk_level': risk_level
    }
