import streamlit as st
import ee
import folium
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import tempfile
import os
from pathlib import Path
import base64
from io import BytesIO
import zipfile
import json
import random

# Import our custom modules
from utils.earth_engine_utils import initialize_ee, get_sentinel_collection, mask_s2_clouds, add_ndvi, add_ndwi
from utils.risk_calculation import calculate_risk_score, calculate_ndvi_change
from utils.visualization import create_risk_map, create_ndvi_comparison_map
from utils.export_utils import export_geotiff, create_zip_export
from utils.node_monitoring import NodeDeploymentSystem, DataFusionEngine, create_node_monitoring_map, simulate_node_data_generation

# Page configuration
st.set_page_config(
    page_title="GeoSafe Landslide Risk Mapper",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .alert-box {
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .alert-warning {
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }
    .alert-danger {
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .alert-success {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
</style>
""", unsafe_allow_html=True)

def main():
    # Header
    st.markdown('<h1 class="main-header">🌍 GeoSafe Landslide Risk Mapper</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    # Initialize session state
    if 'analysis_complete' not in st.session_state:
        st.session_state.analysis_complete = False
    if 'risk_results' not in st.session_state:
        st.session_state.risk_results = None
    if 'node_system' not in st.session_state:
        st.session_state.node_system = NodeDeploymentSystem()
    if 'fusion_engine' not in st.session_state:
        st.session_state.fusion_engine = DataFusionEngine()
    if 'nodes_deployed' not in st.session_state:
        st.session_state.nodes_deployed = False
    
    # Sidebar for controls
    with st.sidebar:
        st.header("🎛️ Analysis Controls")
        
        # ROI Selection
        st.subheader("📍 Region of Interest")
        col1, col2 = st.columns(2)
        with col1:
            min_lon = st.number_input("Min Longitude", value=124.60, format="%.3f", step=0.001)
            min_lat = st.number_input("Min Latitude", value=8.30, format="%.3f", step=0.001)
        with col2:
            max_lon = st.number_input("Max Longitude", value=124.70, format="%.3f", step=0.001)
            max_lat = st.number_input("Max Latitude", value=8.40, format="%.3f", step=0.001)
        
        roi = [min_lon, min_lat, max_lon, max_lat]
        
        # Date Selection
        st.subheader("📅 Time Periods")
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Recent Period**")
            recent_start = st.date_input("Start Date", value=datetime(2025, 1, 1), key="recent_start")
            recent_end = st.date_input("End Date", value=datetime(2025, 10, 1), key="recent_end")
        with col2:
            st.write("**Historical Baseline**")
            hist_start = st.date_input("Start Date", value=datetime(2020, 1, 1), key="hist_start")
            hist_end = st.date_input("End Date", value=datetime(2020, 12, 31), key="hist_end")
        
        # Analysis Parameters
        st.subheader("⚙️ Risk Parameters")
        veg_weight = st.slider("Vegetation Loss Weight", 0.0, 1.0, 0.45, 0.05)
        moisture_weight = st.slider("Moisture Weight", 0.0, 1.0, 0.35, 0.05)
        slope_weight = st.slider("Slope Weight", 0.0, 1.0, 0.20, 0.05)
        
        # Normalize weights
        total_weight = veg_weight + moisture_weight + slope_weight
        if total_weight > 0:
            veg_weight = veg_weight / total_weight
            moisture_weight = moisture_weight / total_weight
            slope_weight = slope_weight / total_weight
        
        # Thresholds
        st.subheader("🎯 Detection Thresholds")
        veg_threshold = st.slider("Vegetation NDVI Threshold", 0.0, 0.5, 0.2, 0.01)
        water_threshold = st.slider("Water NDWI Threshold", 0.0, 0.5, 0.1, 0.01)
        loss_threshold = st.slider("Vegetation Loss Threshold", -0.5, 0.0, -0.15, 0.01)
        
        # Analysis Type
        st.subheader("🔍 Analysis Type")
        analysis_type = st.selectbox(
            "Select Analysis",
            ["NDVI Risk Assessment", "NDVI + Node Monitoring (Synergy)"],
            index=0
        )
        
        # Node Monitoring Controls
        if "Node Monitoring" in analysis_type:
            st.subheader("🌐 Node Monitoring")
            enable_nodes = st.checkbox("Enable Sensor Nodes", value=False, 
                                    help="Deploy simulated sensor nodes for ground monitoring")
            
            if enable_nodes:
                max_nodes = st.slider("Number of Nodes", 1, 10, 5, 
                                     help="Maximum number of sensor nodes to deploy")
                node_placement = st.selectbox(
                    "Node Placement Strategy",
                    ["Auto (Based on Risk Hotspots)", "Manual Selection", "Grid Pattern"],
                    index=0
                )
        
        # Visualization Mode
        st.subheader("🗺️ Visualization Mode")
        viz_mode = st.selectbox(
            "Choose Visualization",
            [
                "Simple Dots (Quick Overview)", 
                "Detailed Layers (Scientific Analysis)",
                "Hybrid View (Both Dots + Layers)",
                "AI Hybrid (Simulated - Proof of Concept)"
            ],
            index=0,
            help="Simple dots: sample points. Detailed layers: continuous patterns. Hybrid: both options. AI Hybrid: AI dots with detailed layers (simulated for proof of concept)."
        )
        
        # Run Analysis Button
        st.markdown("---")
        run_analysis = st.button("🚀 Run Analysis", type="primary", use_container_width=True)
        
        # Export Section
        if st.session_state.analysis_complete:
            st.markdown("---")
            st.subheader("📤 Export Results")
            
            if st.button("💾 Download Results", use_container_width=True):
                if st.session_state.risk_results:
                    zip_buffer = create_zip_export(st.session_state.risk_results)
                    st.download_button(
                        label="📁 Download ZIP",
                        data=zip_buffer,
                        file_name=f"geosafe_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        mime="application/zip"
                    )
    
    # Main content area
    if run_analysis:
        with st.spinner("🔄 Initializing Earth Engine and running analysis..."):
            try:
                # Initialize Earth Engine
                initialize_ee()
                
                # Create ROI geometry
                roi_geometry = ee.Geometry.Rectangle(roi)
                
                # Run NDVI Risk Assessment
                st.session_state.risk_results = run_ndvi_analysis(
                    roi_geometry,
                    recent_start.strftime('%Y-%m-%d'),
                    recent_end.strftime('%Y-%m-%d'),
                    hist_start.strftime('%Y-%m-%d'),
                    hist_end.strftime('%Y-%m-%d'),
                    veg_weight,
                    moisture_weight,
                    slope_weight,
                    veg_threshold,
                    water_threshold,
                    loss_threshold
                )
                # Add visualization mode and ROI bounds to results
                st.session_state.risk_results['viz_mode'] = viz_mode
                st.session_state.risk_results['roi_bounds'] = roi
                
                # Deploy nodes if node monitoring is enabled
                if "Node Monitoring" in analysis_type and enable_nodes:
                    with st.spinner("🌐 Deploying sensor nodes..."):
                        # Suggest node placement
                        node_suggestions = st.session_state.node_system.suggest_node_placement(
                            st.session_state.risk_results, max_nodes
                        )
                        
                        # Deploy nodes
                        deployed_nodes = st.session_state.node_system.deploy_nodes(node_suggestions)
                        st.session_state.nodes_deployed = True
                        st.session_state.risk_results['deployed_nodes'] = deployed_nodes
                        st.session_state.risk_results['node_suggestions'] = node_suggestions
                
                st.session_state.analysis_complete = True
                
            except Exception as e:
                st.error(f"❌ Analysis failed: {str(e)}")
                st.session_state.analysis_complete = False
    
    # Display results
    if st.session_state.analysis_complete and st.session_state.risk_results:
        display_results(st.session_state.risk_results)
        
        # Show node monitoring if nodes are deployed
        if st.session_state.nodes_deployed and 'deployed_nodes' in st.session_state.risk_results:
            display_node_monitoring(st.session_state.risk_results)
    else:
        # Show welcome message and instructions
        show_welcome_message()

def run_ndvi_analysis(roi, recent_start, recent_end, hist_start, hist_end, 
                     veg_weight, moisture_weight, slope_weight, 
                     veg_threshold, water_threshold, loss_threshold):
    """Run the NDVI-based risk analysis"""
    
    # Get satellite data
    with st.spinner("📡 Loading satellite imagery..."):
        recent_collection, recent_dataset = get_sentinel_collection(recent_start, recent_end, roi)
        historical_collection, historical_dataset = get_sentinel_collection(hist_start, hist_end, roi)
    
    # Process images
    with st.spinner("🔄 Processing satellite data..."):
        recent_image = add_ndwi(add_ndvi(recent_collection.map(mask_s2_clouds).median()))
        historical_image = add_ndwi(add_ndvi(historical_collection.map(mask_s2_clouds).median()))
    
    # Calculate risk score
    with st.spinner("🧮 Calculating risk scores..."):
        risk_results = calculate_risk_score(
            recent_image, historical_image, roi,
            veg_weight, moisture_weight, slope_weight,
            veg_threshold, water_threshold
        )
    
    # Calculate NDVI change
    with st.spinner("📊 Analyzing vegetation changes..."):
        ndvi_change = calculate_ndvi_change(
            recent_image, historical_image, roi,
            veg_threshold, water_threshold, loss_threshold
        )
        risk_results.update(ndvi_change)
    
    # Add metadata
    risk_results['metadata'] = {
        'recent_period': f"{recent_start} to {recent_end}",
        'historical_period': f"{hist_start} to {hist_end}",
        'dataset_recent': recent_dataset,
        'dataset_historical': historical_dataset,
        'parameters': {
            'veg_weight': veg_weight,
            'moisture_weight': moisture_weight,
            'slope_weight': slope_weight,
            'veg_threshold': veg_threshold,
            'water_threshold': water_threshold,
            'loss_threshold': loss_threshold
        }
    }
    
    # Add ROI bounds for visualization
    risk_results['roi_bounds'] = roi
    
    return risk_results

def display_results(results):
    """Display analysis results"""
    
    # Results summary
    st.header("📊 Analysis Results")
    
    # Key metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Average NDVI Change",
            f"{results.get('mean_ndvi_change', 0):.4f}",
            delta=f"{results.get('ndvi_change_percent', 0):.1f}%"
        )
    
    with col2:
        st.metric(
            "Risk Threshold",
            f"{results.get('risk_threshold', 0):.3f}",
            help="Threshold for high-risk classification"
        )
    
    with col3:
        st.metric(
            "High-Risk Areas",
            f"{results.get('high_risk_percentage', 0):.1f}%",
            help="Percentage of area classified as high-risk"
        )
    
    with col4:
        risk_level = results.get('risk_level', 'Unknown')
        st.metric(
            "Risk Level",
            risk_level,
            help="Overall risk assessment"
        )
    
    # Alert message
    alert_message = results.get('alert_message', '')
    alert_type = results.get('alert_type', 'info')
    
    if alert_message:
        if alert_type == 'danger':
            st.markdown(f'<div class="alert-box alert-danger">{alert_message}</div>', unsafe_allow_html=True)
        elif alert_type == 'warning':
            st.markdown(f'<div class="alert-box alert-warning">{alert_message}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="alert-box alert-success">{alert_message}</div>', unsafe_allow_html=True)
    
    # Interactive map
    st.header("🗺️ Interactive Risk Map")
    
    # Create map
    risk_map = create_risk_map(results)
    
    # Display map
    st.components.v1.html(risk_map._repr_html_(), height=600)
    
    # Detailed results
    with st.expander("📋 Detailed Results"):
        st.subheader("Analysis Parameters")
        metadata = results.get('metadata', {})
        params = metadata.get('parameters', {})
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Recent Period:** {metadata.get('recent_period', 'N/A')}")
            st.write(f"**Historical Period:** {metadata.get('historical_period', 'N/A')}")
            st.write(f"**Recent Dataset:** {metadata.get('dataset_recent', 'N/A')}")
            st.write(f"**Historical Dataset:** {metadata.get('dataset_historical', 'N/A')}")
        
        with col2:
            st.write(f"**Vegetation Weight:** {params.get('veg_weight', 0):.2f}")
            st.write(f"**Moisture Weight:** {params.get('moisture_weight', 0):.2f}")
            st.write(f"**Slope Weight:** {params.get('slope_weight', 0):.2f}")
            st.write(f"**Vegetation Threshold:** {params.get('veg_threshold', 0):.2f}")
    
    # Export section
    st.header("📤 Export Results")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 Export Risk Score"):
            if 'risk_score' in results:
                export_geotiff(results['risk_score'], "risk_score.tif")
                st.success("Risk score exported!")
    
    with col2:
        if st.button("🔥 Export Hotspots"):
            if 'risk_hotspots' in results:
                export_geotiff(results['risk_hotspots'], "risk_hotspots.tif")
                st.success("Risk hotspots exported!")
    
    with col3:
        if st.button("📈 Export NDVI Change"):
            if 'ndvi_change' in results:
                export_geotiff(results['ndvi_change'], "ndvi_change.tif")
                st.success("NDVI change exported!")

def display_node_monitoring(results):
    """Display node monitoring dashboard"""
    
    st.header("🌐 Sensor Node Monitoring Dashboard")
    st.markdown("---")
    
    # Get deployed nodes
    deployed_nodes = results.get('deployed_nodes', [])
    node_system = st.session_state.node_system
    
    if not deployed_nodes:
        st.warning("No sensor nodes deployed. Enable node monitoring in the analysis settings.")
        return
    
    # Node status overview
    st.subheader("📊 Node Status Overview")
    
    # Create columns for node status
    cols = st.columns(min(len(deployed_nodes), 4))
    
    for i, node in enumerate(deployed_nodes):
        with cols[i % 4]:
            status = node.get_status_summary()
            latest_reading = status.get('latest_reading', {})
            
            # Status color
            if status['battery_level'] < 20:
                status_color = "🔴"
            elif status['battery_level'] < 50:
                status_color = "🟡"
            else:
                status_color = "🟢"
            
            st.metric(
                f"{status_color} {node.node_id}",
                f"Battery: {status['battery_level']:.1f}%",
                f"Risk: {node.risk_level.upper()}"
            )
    
    # Real-time sensor readings
    st.subheader("📡 Real-time Sensor Readings")
    
    # Generate fresh readings for all nodes
    if st.button("🔄 Refresh Sensor Data", key="refresh_sensors"):
        st.rerun()
    
    # Display sensor data in tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🌡️ Environmental", "🌱 Soil Sensors", "📐 Movement", "📊 Data Fusion"])
    
    with tab1:
        st.subheader("Environmental Sensors")
        
        env_cols = st.columns(len(deployed_nodes))
        for i, node in enumerate(deployed_nodes):
            with env_cols[i]:
                reading = node.generate_sensor_reading()
                st.write(f"**{node.node_id}**")
                st.metric("Temperature", f"{reading['temperature']:.1f}°C")
                st.metric("Humidity", f"{reading['humidity']:.1f}%")
                st.metric("Pressure", f"{reading['pressure']:.1f} hPa")
    
    with tab2:
        st.subheader("Soil Moisture Sensors")
        
        soil_cols = st.columns(len(deployed_nodes))
        for i, node in enumerate(deployed_nodes):
            with soil_cols[i]:
                reading = node.generate_sensor_reading()
                soil_moisture = reading['soil_moisture']
                
                # Risk assessment based on soil moisture
                if soil_moisture > 70:
                    risk_level = "🔴 High Risk"
                elif soil_moisture > 50:
                    risk_level = "🟡 Moderate Risk"
                else:
                    risk_level = "🟢 Low Risk"
                
                st.write(f"**{node.node_id}**")
                st.metric("Soil Moisture", f"{soil_moisture:.1f}%", risk_level)
    
    with tab3:
        st.subheader("Movement & Vibration Sensors")
        
        movement_cols = st.columns(len(deployed_nodes))
        for i, node in enumerate(deployed_nodes):
            with movement_cols[i]:
                reading = node.generate_sensor_reading()
                
                # Calculate total tilt
                total_tilt = np.sqrt(reading['tilt_x']**2 + reading['tilt_y']**2 + reading['tilt_z']**2)
                vibration = reading['vibration']
                
                st.write(f"**{node.node_id}**")
                st.metric("Total Tilt", f"{total_tilt:.3f}°")
                st.metric("Vibration", f"{vibration:.4f}")
                
                # Alert if significant movement
                if total_tilt > 1.0 or vibration > 0.5:
                    st.warning("⚠️ Significant movement detected!")
    
    with tab4:
        st.subheader("Data Fusion Analysis")
        st.write("Combining satellite data with ground sensor readings for enhanced risk assessment...")
        
        # Fusion analysis for each node
        fusion_cols = st.columns(len(deployed_nodes))
        for i, node in enumerate(deployed_nodes):
            with fusion_cols[i]:
                reading = node.generate_sensor_reading()
                
                # Get satellite risk for this location (simplified)
                satellite_risk = 0.5 + random.uniform(-0.2, 0.3)  # Simulate satellite risk
                
                # Fuse data
                fusion_result = st.session_state.fusion_engine.fuse_data(satellite_risk, reading)
                
                st.write(f"**{node.node_id}**")
                st.metric("Fused Risk Score", f"{fusion_result['fused_risk_score']:.3f}")
                st.metric("Confidence", f"{fusion_result['confidence_level']:.1%}")
                
                # Risk level based on fused data
                fused_risk = fusion_result['fused_risk_score']
                if fused_risk > 0.7:
                    risk_status = "🔴 HIGH RISK"
                elif fused_risk > 0.5:
                    risk_status = "🟡 MODERATE RISK"
                else:
                    risk_status = "🟢 LOW RISK"
                
                st.write(f"**Status:** {risk_status}")
    
    # Node monitoring map
    st.subheader("🗺️ Node Deployment Map")
    
    # Create node monitoring map
    node_map = create_node_monitoring_map(node_system.nodes, results)
    st.components.v1.html(node_map._repr_html_(), height=500)
    
    # Data export for nodes
    st.subheader("📤 Export Node Data")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 Export Sensor Data"):
            # Generate 24 hours of simulated data
            simulation_data = simulate_node_data_generation(node_system.nodes, 24)
            
            # Create CSV export
            all_data = []
            for node_id, readings in simulation_data.items():
                for reading in readings:
                    reading['node_id'] = node_id
                    all_data.append(reading)
            
            df = pd.DataFrame(all_data)
            csv = df.to_csv(index=False)
            
            st.download_button(
                label="📁 Download Sensor Data (CSV)",
                data=csv,
                file_name=f"geosafe_sensor_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    with col2:
        if st.button("🌐 Export Node Locations"):
            # Export node locations as GeoJSON
            node_locations = []
            for node in deployed_nodes:
                node_locations.append({
                    'type': 'Feature',
                    'properties': {
                        'node_id': node.node_id,
                        'risk_level': node.risk_level,
                        'battery_level': node.battery_level,
                        'status': node.status
                    },
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [node.longitude, node.latitude]
                    }
                })
            
            geojson = {
                'type': 'FeatureCollection',
                'features': node_locations
            }
            
            st.download_button(
                label="📁 Download Node Locations (GeoJSON)",
                data=json.dumps(geojson, indent=2),
                file_name=f"geosafe_node_locations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.geojson",
                mime="application/json"
            )

def show_welcome_message():
    """Show welcome message and instructions"""
    
    st.markdown("""
    ## 🌍 Welcome to GeoSafe Landslide Risk Mapper
    
    This application provides comprehensive landslide risk assessment using:
    - **Sentinel-2 imagery** for vegetation analysis
    - **NDVI/NDWI indices** for environmental monitoring  
    - **Slope analysis** from SRTM DEM
    - **Risk scoring** based on multiple factors
    - **🌐 NEW: Sensor Node Monitoring** for ground-level validation
    
    ### 🚀 How to Use:
    1. **Configure your analysis** using the sidebar controls
    2. **Select your region** by adjusting the ROI coordinates
    3. **Set time periods** for recent and historical comparison
    4. **Choose analysis type** - Standard or with Node Monitoring
    5. **Adjust parameters** to fine-tune the analysis
    6. **Click "Run Analysis"** to start processing
    7. **View results** on the interactive map
    8. **Monitor sensor nodes** (if enabled) for real-time ground data
    9. **Export data** for further analysis
    
    ### 🌐 NEW: Node Monitoring Synergy:
    - **Smart Deployment**: AI-driven node placement based on satellite risk analysis
    - **Multi-Sensor Simulation**: Soil moisture, tilt, vibration, environmental sensors
    - **Data Fusion**: Combines satellite + ground sensor data for enhanced accuracy
    - **Real-time Monitoring**: Live dashboard with sensor readings and alerts
    - **Proof of Concept**: Demonstrates satellite-ground sensor synergy
    
    ### 📍 Default Settings:
    - **Region:** Baungon, Bukidnon, Philippines
    - **Recent Period:** 2025 (current year)
    - **Historical Baseline:** 2020
    - **Risk Weights:** Vegetation (45%), Moisture (35%), Slope (20%)
    
    ### ⚠️ Important Notes:
    - Ensure you have a **Google Earth Engine account** and are authenticated
    - Analysis may take **2-5 minutes** depending on region size
    - Results are automatically saved to the `outputs/` folder
    - Large regions may require longer processing times
    - **Node monitoring** is simulated for proof of concept
    
    **Ready to start?** Use the sidebar to configure your analysis! 🎯
    """)
    
    # Show system status
    st.markdown("---")
    st.subheader("🔧 System Status")
    
    try:
        # Check Earth Engine connection
        ee.Initialize()
        st.success("✅ Google Earth Engine: Connected")
    except:
        st.warning("⚠️ Google Earth Engine: Not connected - authentication required")
    
    # Check dependencies
    try:
        import folium
        st.success("✅ Folium: Available")
    except:
        st.error("❌ Folium: Missing")
    
    try:
        import pandas
        st.success("✅ Pandas: Available")
    except:
        st.error("❌ Pandas: Missing")

if __name__ == "__main__":
    main()
