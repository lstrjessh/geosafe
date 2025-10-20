"""
Export utilities for GeoSafe Landslide Risk Mapper
"""

import os
import zipfile
import tempfile
from pathlib import Path
import streamlit as st

def export_geotiff(ee_image, filename):
    """Export Earth Engine image as GeoTIFF"""
    # This is a simplified version - in practice, you'd need to:
    # 1. Use geemap.ee_export_image() or similar
    # 2. Save to a temporary file
    # 3. Return the file path or bytes
    
    # For now, create a placeholder file
    output_dir = Path('outputs')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = output_dir / filename
    
    # Create a placeholder file (in real implementation, this would be the actual GeoTIFF)
    with open(file_path, 'w') as f:
        f.write(f"# Placeholder for {filename}\n")
        f.write("# In a real implementation, this would be a GeoTIFF file\n")
        f.write(f"# Generated from Earth Engine image: {ee_image}\n")
    
    return file_path

def create_zip_export(results):
    """Create a ZIP file with all exportable results"""
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Export risk score
        if 'risk_score' in results:
            export_geotiff(results['risk_score'], 'risk_score.tif')
        
        # Export risk hotspots
        if 'risk_hotspots' in results:
            export_geotiff(results['risk_hotspots'], 'risk_hotspots.tif')
        
        # Export NDVI change
        if 'ndvi_change' in results:
            export_geotiff(results['ndvi_change'], 'ndvi_change.tif')
        
        # Create metadata file
        metadata_file = temp_path / 'metadata.txt'
        with open(metadata_file, 'w') as f:
            f.write("GeoSafe Landslide Risk Mapper - Export Results\n")
            f.write("=" * 50 + "\n\n")
            
            metadata = results.get('metadata', {})
            f.write(f"Recent Period: {metadata.get('recent_period', 'N/A')}\n")
            f.write(f"Historical Period: {metadata.get('historical_period', 'N/A')}\n")
            f.write(f"Recent Dataset: {metadata.get('dataset_recent', 'N/A')}\n")
            f.write(f"Historical Dataset: {metadata.get('dataset_historical', 'N/A')}\n\n")
            
            params = metadata.get('parameters', {})
            f.write("Analysis Parameters:\n")
            f.write(f"  Vegetation Weight: {params.get('veg_weight', 0):.2f}\n")
            f.write(f"  Moisture Weight: {params.get('moisture_weight', 0):.2f}\n")
            f.write(f"  Slope Weight: {params.get('slope_weight', 0):.2f}\n")
            f.write(f"  Vegetation Threshold: {params.get('veg_threshold', 0):.2f}\n")
            f.write(f"  Water Threshold: {params.get('water_threshold', 0):.2f}\n")
            f.write(f"  Loss Threshold: {params.get('loss_threshold', 0):.2f}\n\n")
            
            f.write("Results Summary:\n")
            f.write(f"  Risk Threshold: {results.get('risk_threshold', 0):.3f}\n")
            f.write(f"  High Risk Percentage: {results.get('high_risk_percentage', 0):.1f}%\n")
            f.write(f"  Mean NDVI Change: {results.get('mean_ndvi_change', 0):.4f}\n")
            f.write(f"  Risk Level: {results.get('risk_level', 'Unknown')}\n")
        
        # Create ZIP file
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add all files from outputs directory
            outputs_dir = Path('outputs')
            if outputs_dir.exists():
                for file_path in outputs_dir.glob('*'):
                    if file_path.is_file():
                        zip_file.write(file_path, file_path.name)
            
            # Add metadata file
            zip_file.write(metadata_file, 'metadata.txt')
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()

def create_summary_report(results):
    """Create a summary report of the analysis"""
    
    report = f"""
# GeoSafe Landslide Risk Assessment Report

## Analysis Summary
- **Risk Level**: {results.get('risk_level', 'Unknown')}
- **Risk Threshold**: {results.get('risk_threshold', 0):.3f}
- **High Risk Areas**: {results.get('high_risk_percentage', 0):.1f}%

## NDVI Change Analysis
- **Mean NDVI Change**: {results.get('mean_ndvi_change', 0):.4f}
- **Change Percentage**: {results.get('ndvi_change_percent', 0):.1f}%

## Alert Status
{results.get('alert_message', 'No alerts generated')}

## Recommendations
"""
    
    if results.get('risk_level') == 'High':
        report += """
- **IMMEDIATE ACTION REQUIRED**: Deploy Geo-Safe Sensor Nodes
- Monitor area closely for ground movement
- Consider evacuation planning if risk persists
- Implement slope stabilization measures
"""
    elif results.get('risk_level') == 'Low':
        report += """
- Continue routine satellite monitoring
- No immediate action required
- Maintain current monitoring schedule
"""
    else:
        report += """
- Monitor area for changes
- Review analysis parameters if needed
- Consider additional ground verification
"""
    
    return report
