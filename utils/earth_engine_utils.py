"""
Earth Engine utility functions for GeoSafe Landslide Risk Mapper
"""

import ee
import streamlit as st

def initialize_ee():
    """Initialize Google Earth Engine with authentication"""
    
    # List of project IDs to try
    projects_to_try = [
        'philsa-475509',  # Your specific project ID
        None,  # No project specified (fallback)
        'earthengine-legacy',
        'earthengine-public',
        'philsa',  # Legacy project name
    ]
    
    for i, project in enumerate(projects_to_try):
        try:
            if project:
                ee.Initialize(project=project)
                st.success(f"✅ Earth Engine initialized with project: {project}")
            else:
                ee.Initialize()
                st.success("✅ Earth Engine initialized successfully")
            return True
            
        except Exception as e:
            if i == len(projects_to_try) - 1:  # Last attempt
                st.error(f"❌ Earth Engine initialization failed: {str(e)}")
                
                # Provide helpful instructions
                st.markdown("""
                ### 🔧 Earth Engine Setup Required
                
                **Quick Fix Options:**
                
                **Option 1: Force re-authentication**
                ```bash
                earthengine authenticate --force
                ```
                
                **Option 2: Use Demo Mode (No Earth Engine needed)**
                ```bash
                streamlit run app_demo.py
                ```
                
                **Option 3: Set up Google Cloud Project**
                1. Go to [Google Cloud Console](https://console.cloud.google.com/)
                2. Create a new project or select existing one
                3. Enable Earth Engine API
                4. Run: `gcloud auth login`
                
                **Option 4: Check your project permissions**
                - Visit: https://console.cloud.google.com/iam-admin/iam
                - Ensure you have "Earth Engine User" role
                """)
                
                # Add a button to switch to demo mode
                if st.button("🎯 Switch to Demo Mode", type="primary"):
                    st.switch_page("app_demo.py")
                
                return False
            else:
                continue  # Try next project
    
    return False

def mask_s2_clouds(image):
    """Mask clouds in a Sentinel-2 image using the QA60 band."""
    qa = image.select('QA60')
    cloud_bit_mask = 1 << 10
    cirrus_bit_mask = 1 << 11
    mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
    return image.updateMask(mask).divide(10000)

def add_ndvi(image):
    """Add an NDVI band to a Sentinel-2 image."""
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
    return image.addBands(ndvi)

def add_ndwi(image):
    """Add an NDWI band to a Sentinel-2 image."""
    ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
    return image.addBands(ndwi)

def get_sentinel_collection(start_date, end_date, region, max_cloud=20):
    """Get Sentinel-2 collection with fallback to different datasets"""
    sr_id = 'COPERNICUS/S2_SR_HARMONIZED'
    sr_collection = (
        ee.ImageCollection(sr_id)
        .filterDate(start_date, end_date)
        .filterBounds(region)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud))
    )

    sr_count = sr_collection.size().getInfo() or 0
    if sr_count > 0:
        return sr_collection, sr_id

    toa_id = 'COPERNICUS/S2'
    toa_collection = (
        ee.ImageCollection(toa_id)
        .filterDate(start_date, end_date)
        .filterBounds(region)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', max_cloud))
    )

    toa_count = toa_collection.size().getInfo() or 0
    if toa_count == 0:
        raise RuntimeError(
            f'No Sentinel-2 imagery available for {start_date} to {end_date} in the selected ROI.'
        )

    return toa_collection, toa_id

def get_slope_data(roi):
    """Get slope data from SRTM DEM"""
    dem = ee.Image('USGS/SRTMGL1_003').clip(roi)
    slope = ee.Algorithms.Terrain(dem).select('slope')
    return slope

def get_soil_moisture_data(start_date, end_date, roi):
    """Get soil moisture data from SMAP if available"""
    try:
        soil_moisture_dataset = 'NASA_USDA/HSL/SMAP10KM_soil_moisture'
        soil_moisture_collection = (
            ee.ImageCollection(soil_moisture_dataset)
            .filterDate(start_date, end_date)
            .filterBounds(roi)
        )
        soil_moisture_count = soil_moisture_collection.size().getInfo() or 0
        if soil_moisture_count > 0:
            soil_moisture_layer = soil_moisture_collection.select('ssm').mean().clip(roi)
            return soil_moisture_layer, soil_moisture_count
        else:
            return None, 0
    except Exception:
        return None, 0
