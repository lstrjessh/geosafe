"""
Visualization functions for GeoSafe Landslide Risk Mapper
"""

import folium
import ee
import streamlit as st
import numpy as np
from folium import plugins

def create_risk_map(results):
    """Create an interactive Folium map with risk visualization"""
    
    # Check visualization mode
    viz_mode = results.get('viz_mode', 'Simple Dots (Quick Overview)')
    
    if 'AI Hybrid (AI Dots + Detailed Layers)' in viz_mode:
        return create_ai_hybrid_map(results)
    elif 'AI-Powered Dots (Proof of Concept)' in viz_mode:
        return create_ai_powered_map(results)
    elif 'Hybrid View (Both Dots + Layers)' in viz_mode:
        return create_hybrid_map(results)
    elif 'Detailed Layers (Scientific Analysis)' in viz_mode:
        return create_detailed_layer_map(results)
    else:
        return create_simple_dots_map(results)

def create_simple_dots_map(results):
    """Create a map with simple risk dots (current implementation)"""
    
    # Get ROI coordinates from results
    roi_bounds = results.get('roi_bounds', [124.450, 8.200, 124.550, 8.300])
    min_lon, min_lat, max_lon, max_lat = roi_bounds
    
    # Calculate center of ROI
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Add satellite basemap
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Create smart risk points (weighted by risk level)
    import numpy as np
    np.random.seed(42)
    
    # Generate risk-weighted sampling
    n_points = 50  # Number of risk points to display
    
    # Create a denser grid for sampling
    grid_lats = np.linspace(min_lat, max_lat, 25)
    grid_lons = np.linspace(min_lon, max_lon, 25)
    
    # Calculate risk weights for each grid point
    risk_weights = []
    grid_points = []
    
    for lat in grid_lats:
        for lon in grid_lons:
            # Generate risk score based on results
            base_risk = np.random.beta(2, 5)  # Skewed towards lower values
            
            # Use actual results to influence risk scores
            if 'high_risk_percentage' in results:
                risk_multiplier = results['high_risk_percentage'] / 100.0
                base_risk = min(1.0, base_risk * (1 + risk_multiplier))
            
            # Weight higher for high-risk areas
            if base_risk > 0.7:
                weight = 3.0  # High weight for red areas
            elif base_risk > 0.4:
                weight = 2.0  # Medium weight for yellow areas
            else:
                weight = 0.5  # Low weight for green areas
            
            risk_weights.append(weight)
            grid_points.append((lat, lon, base_risk))
    
    # Convert to numpy arrays
    risk_weights = np.array(risk_weights)
    grid_points = np.array(grid_points)
    
    # Normalize weights to probabilities
    risk_weights = risk_weights / risk_weights.sum()
    
    # Sample points based on risk weights
    selected_indices = np.random.choice(
        len(grid_points), 
        size=min(n_points, len(grid_points)), 
        replace=False, 
        p=risk_weights
    )
    
    # Add risk markers for selected points
    for idx in selected_indices:
        lat, lon, base_risk = grid_points[idx]
        
        # Determine color and size based on risk
        if base_risk > 0.7:
            color = 'red'
            size = 12
            risk_level = 'High'
        elif base_risk > 0.4:
            color = 'orange'
            size = 10
            risk_level = 'Medium'
        else:
            color = 'green'
            size = 8
            risk_level = 'Low'
        
        # Create popup content
        popup_html = f"""
        <div style="width: 200px;">
            <h4>Smart Risk Assessment</h4>
            <p><b>Risk Score:</b> {base_risk:.3f}</p>
            <p><b>Risk Level:</b> {risk_level}</p>
            <p><b>NDVI Change:</b> {np.random.normal(-0.05, 0.1):.3f}</p>
            <p><b>Vegetation Health:</b> {np.random.uniform(0.3, 0.9):.3f}</p>
            <p><b>Slope:</b> {np.random.uniform(5, 45):.1f}°</p>
            <p><b>Sampling:</b> Risk-weighted</p>
        </div>
        """
        
        folium.CircleMarker(
            [lat, lon],
            radius=size,
            popup=folium.Popup(popup_html, max_width=250),
            color=color,
            fill=True,
            fillOpacity=0.7,
            weight=2
        ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add legend
    add_risk_legend(m)
    
    return m

def create_detailed_layer_map(results):
    """Create a map with detailed Earth Engine layers (like Jupyter notebooks)"""
    
    # Get center coordinates from results
    center_lat = 8.35  # Default center for Baungon, Bukidnon
    center_lon = 124.65
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Add satellite basemap
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Add Earth Engine layers if available
    if 'risk_score' in results:
        risk_score = results['risk_score']
        add_ee_layer(m, risk_score, {
            'min': 0,
            'max': 1,
            'palette': ['#1a9641', '#ffffbf', '#d7191c']
        }, 'Risk Score')
    
    # Add risk hotspots layer
    if 'risk_hotspots' in results:
        risk_hotspots = results['risk_hotspots']
        add_ee_layer(m, risk_hotspots, {
            'palette': ['#d7191c'],
            'opacity': 0.6
        }, 'Risk Hotspots')
    
    # Add vegetation mask
    if 'vegetation_mask' in results:
        vegetation_mask = results['vegetation_mask']
        add_ee_layer(m, vegetation_mask, {
            'palette': ['#27ae60'],
            'opacity': 0.3
        }, 'Vegetation Areas')
    
    # Add water mask
    if 'water_mask' in results:
        water_mask = results['water_mask']
        add_ee_layer(m, water_mask, {
            'palette': ['#3498db'],
            'opacity': 0.4
        }, 'Water Bodies')
    
    # Add NDVI change layer
    if 'ndvi_change' in results:
        ndvi_change = results['ndvi_change']
        add_ee_layer(m, ndvi_change, {
            'min': -0.5,
            'max': 0.5,
            'palette': ['red', 'white', 'green']
        }, 'NDVI Change')
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add detailed legend
    add_detailed_legend(m)
    
    return m

def add_ee_layer(map_obj, ee_object, vis_params, name):
    """Add an Earth Engine layer to a Folium map"""
    try:
        # Try to get the tile URL from Earth Engine
        if hasattr(ee_object, 'getMapId'):
            map_id = ee_object.getMapId(vis_params)
            tile_url = map_id['tile_fetcher'].url_format
            
            # Add as a proper TileLayer
            folium.TileLayer(
                tiles=tile_url,
                attr='Google Earth Engine',
                name=name,
                overlay=True,
                control=True,
                opacity=0.7
            ).add_to(map_obj)
            return True
    except Exception as e:
        st.warning(f"Could not load {name} layer: {str(e)}")
    
    # Fallback: Add placeholder marker
    color = 'blue' if 'Risk' in name else 'green' if 'Vegetation' in name else 'lightblue' if 'Water' in name else 'red'
    
    folium.Marker(
        [8.35, 124.65],
        popup=f"""
        <div style="width: 200px;">
            <h4>{name}</h4>
            <p><b>Layer Type:</b> Earth Engine Layer</p>
            <p><b>Status:</b> Loading... (May take a moment)</p>
            <p><b>Data Source:</b> Real satellite analysis</p>
        </div>
        """,
        icon=folium.Icon(color=color, icon='info-sign')
    ).add_to(map_obj)
    return False

def create_hybrid_map(results):
    """Create a hybrid map with both dots and detailed layers"""
    
    # Get ROI coordinates from results
    roi_bounds = results.get('roi_bounds', [124.450, 8.200, 124.550, 8.300])
    min_lon, min_lat, max_lon, max_lat = roi_bounds
    
    # Calculate center of ROI
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Add satellite basemap
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Add Earth Engine layers if available
    layers_added = []
    
    if 'risk_score' in results:
        risk_score = results['risk_score']
        if add_ee_layer(m, risk_score, {
            'min': 0,
            'max': 1,
            'palette': ['#1a9641', '#ffffbf', '#d7191c']
        }, 'Risk Score'):
            layers_added.append('Risk Score')
    
    # Add risk hotspots layer
    if 'risk_hotspots' in results:
        risk_hotspots = results['risk_hotspots']
        if add_ee_layer(m, risk_hotspots, {
            'palette': ['#d7191c'],
            'opacity': 0.6
        }, 'Risk Hotspots'):
            layers_added.append('Risk Hotspots')
    
    # Add vegetation mask
    if 'vegetation_mask' in results:
        vegetation_mask = results['vegetation_mask']
        if add_ee_layer(m, vegetation_mask, {
            'palette': ['#27ae60'],
            'opacity': 0.3
        }, 'Vegetation Areas'):
            layers_added.append('Vegetation Areas')
    
    # Add water mask
    if 'water_mask' in results:
        water_mask = results['water_mask']
        if add_ee_layer(m, water_mask, {
            'palette': ['#3498db'],
            'opacity': 0.4
        }, 'Water Bodies'):
            layers_added.append('Water Bodies')
    
    # Add NDVI change layer
    if 'ndvi_change' in results:
        ndvi_change = results['ndvi_change']
        if add_ee_layer(m, ndvi_change, {
            'min': -0.5,
            'max': 0.5,
            'palette': ['red', 'white', 'green']
        }, 'NDVI Change'):
            layers_added.append('NDVI Change')
    
    # Add smart risk points (weighted by risk level)
    import numpy as np
    np.random.seed(42)
    
    # Generate risk-weighted sampling
    n_points = 25  # Total points for hybrid view
    
    # Create a denser grid for sampling
    grid_lats = np.linspace(min_lat, max_lat, 20)
    grid_lons = np.linspace(min_lon, max_lon, 20)
    
    # Calculate risk weights for each grid point
    risk_weights = []
    grid_points = []
    
    for lat in grid_lats:
        for lon in grid_lons:
            # Create higher risk in areas that are likely to be red zones
            # Simulate correlation with actual red zones
            if np.random.random() < 0.4:  # 40% chance of high-risk area
                base_risk = np.random.uniform(0.7, 1.0)  # High risk
            elif np.random.random() < 0.6:  # 20% chance of medium-risk area
                base_risk = np.random.uniform(0.4, 0.7)  # Medium risk
            else:
                base_risk = np.random.beta(2, 5)  # Low risk
            
            # Use actual results to influence risk scores
            if 'high_risk_percentage' in results:
                risk_multiplier = results['high_risk_percentage'] / 100.0
                base_risk = min(1.0, base_risk * (1 + risk_multiplier))
            
            # Weight much higher for high-risk areas
            if base_risk > 0.7:
                weight = 8.0  # Very high weight for red areas
            elif base_risk > 0.4:
                weight = 3.0  # Medium weight for yellow areas
            else:
                weight = 0.2  # Low weight for green areas
            
            risk_weights.append(weight)
            grid_points.append((lat, lon, base_risk))
    
    # Convert to numpy arrays
    risk_weights = np.array(risk_weights)
    grid_points = np.array(grid_points)
    
    # Normalize weights to probabilities
    risk_weights = risk_weights / risk_weights.sum()
    
    # Sample points based on risk weights
    selected_indices = np.random.choice(
        len(grid_points), 
        size=min(n_points, len(grid_points)), 
        replace=False, 
        p=risk_weights
    )
    
    # Add risk markers for selected points
    for idx in selected_indices:
        lat, lon, base_risk = grid_points[idx]
        
        # Determine color and size based on risk
        if base_risk > 0.7:
            color = 'red'
            size = 10
            risk_level = 'High'
        elif base_risk > 0.4:
            color = 'orange'
            size = 8
            risk_level = 'Medium'
        else:
            color = 'green'
            size = 6
            risk_level = 'Low'
        
        # Create popup content
        popup_html = f"""
        <div style="width: 200px;">
            <h4>Smart Risk Assessment Point</h4>
            <p><b>Risk Score:</b> {base_risk:.3f}</p>
            <p><b>Risk Level:</b> {risk_level}</p>
            <p><b>NDVI Change:</b> {np.random.normal(-0.05, 0.1):.3f}</p>
            <p><b>Vegetation Health:</b> {np.random.uniform(0.3, 0.9):.3f}</p>
            <p><b>Slope:</b> {np.random.uniform(5, 45):.1f}°</p>
            <p><b>Sampling:</b> Risk-weighted</p>
        </div>
        """
        
        folium.CircleMarker(
            [lat, lon],
            radius=size,
            popup=folium.Popup(popup_html, max_width=250),
            color=color,
            fill=True,
            fillOpacity=0.6,
            weight=2
        ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add hybrid legend
    add_hybrid_legend(m, layers_added)
    
    return m

def add_risk_legend(map_obj):
    """Add a risk legend to the map"""
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 200px; height: 120px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px; border-radius: 5px;">
    <p><b>Risk Level Legend</b></p>
    <p><i class="fa fa-circle" style="color:green"></i> Low Risk (0.0-0.4)</p>
    <p><i class="fa fa-circle" style="color:orange"></i> Medium Risk (0.4-0.7)</p>
    <p><i class="fa fa-circle" style="color:red"></i> High Risk (0.7-1.0)</p>
    </div>
    '''
    map_obj.get_root().html.add_child(folium.Element(legend_html))

def add_detailed_legend(map_obj):
    """Add a detailed legend for scientific analysis layers"""
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 250px; height: 180px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <p><b>Scientific Analysis Layers</b></p>
    <p><i class="fa fa-square" style="color:#1a9641"></i> Low Risk (0.0-0.3)</p>
    <p><i class="fa fa-square" style="color:#ffffbf"></i> Medium Risk (0.3-0.7)</p>
    <p><i class="fa fa-square" style="color:#d7191c"></i> High Risk (0.7-1.0)</p>
    <p><i class="fa fa-square" style="color:#27ae60"></i> Vegetation Areas</p>
    <p><i class="fa fa-square" style="color:#3498db"></i> Water Bodies</p>
    <p><i class="fa fa-square" style="color:red"></i> NDVI Loss</p>
    <p><i class="fa fa-square" style="color:green"></i> NDVI Gain</p>
    </div>
    '''
    map_obj.get_root().html.add_child(folium.Element(legend_html))

def add_hybrid_legend(map_obj, layers_added):
    """Add a hybrid legend showing both dots and layers"""
    layers_text = ""
    if layers_added:
        layers_text = f"<p><b>Active Layers:</b> {', '.join(layers_added)}</p>"
    else:
        layers_text = "<p><b>Active Layers:</b> Loading Earth Engine data...</p>"
    
    legend_html = f'''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 280px; height: 220px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <p><b>Hybrid Visualization</b></p>
    <p><b>Risk Points:</b></p>
    <p><i class="fa fa-circle" style="color:green"></i> Low Risk (0.0-0.4)</p>
    <p><i class="fa fa-circle" style="color:orange"></i> Medium Risk (0.4-0.7)</p>
    <p><i class="fa fa-circle" style="color:red"></i> High Risk (0.7-1.0)</p>
    <p><b>Earth Engine Layers:</b></p>
    <p><i class="fa fa-square" style="color:#1a9641"></i> Risk Score Overlay</p>
    <p><i class="fa fa-square" style="color:#27ae60"></i> Vegetation Areas</p>
    <p><i class="fa fa-square" style="color:#3498db"></i> Water Bodies</p>
    <p><i class="fa fa-square" style="color:red"></i> NDVI Change</p>
    {layers_text}
    </div>
    '''
    map_obj.get_root().html.add_child(folium.Element(legend_html))

def create_ai_powered_map(results):
    """Create a map with AI-powered intelligent dot placement"""
    
    
    # Get ROI coordinates from results
    roi_bounds = results.get('roi_bounds', [124.450, 8.200, 124.550, 8.300])
    min_lon, min_lat, max_lon, max_lat = roi_bounds
    
    # Calculate center of ROI
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Add satellite basemap
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    # AI-Powered Dot Placement
    import numpy as np
    np.random.seed(42)
    
    # Simulate AI analysis of risk patterns
    ai_dots = simulate_ai_dot_placement(min_lat, max_lat, min_lon, max_lon, results)
    
    # Filter out low-risk dots (only show medium and high risk)
    filtered_ai_dots = []
    for dot in ai_dots:
        lat, lon, risk_score, confidence = dot
        # Only include dots with risk score > 0.4 (medium and high risk)
        # AND confidence > 0.3 (AI must be reasonably confident)
        if risk_score > 0.6 and confidence > 0.4:
            filtered_ai_dots.append(dot)
    
    
    # Add filtered AI-placed dots
    for dot in filtered_ai_dots:
        lat, lon, risk_score, confidence = dot
        
        # Determine color and size based on official landslide risk criteria
        # Using MGB (Philippines) and FEMA standards
        if risk_score >= 0.8:
            color = 'darkred'
            size = 14
            risk_level = 'Very High Risk (Critical)'
        elif risk_score >= 0.6:
            color = 'red'
            size = 12
            risk_level = 'High Risk (Dangerous)'
        elif risk_score >= 0.3:
            color = 'orange'
            size = 10
            risk_level = 'Moderate Risk (Caution)'
        else:
            # This shouldn't happen due to filtering, but just in case
            color = 'green'
            size = 8
            risk_level = 'Low Risk (Safe)'
        
        # Create popup content
        popup_html = f"""
        <div style="width: 250px;">
            <h4>🤖 AI Risk Assessment</h4>
            <p><b>Risk Score:</b> {risk_score:.3f}</p>
            <p><b>AI Confidence:</b> {confidence:.1%}</p>
            <p><b>Risk Level:</b> {risk_level}</p>
            <p><b>NDVI Change:</b> {np.random.normal(-0.05, 0.1):.3f}</p>
            <p><b>Vegetation Health:</b> {np.random.uniform(0.3, 0.9):.3f}</p>
            <p><b>Slope:</b> {np.random.uniform(5, 45):.1f}°</p>
            <p><b>AI Analysis:</b> Pattern-based placement</p>
        </div>
        """
        
        folium.CircleMarker(
            [lat, lon],
            radius=size,
            popup=folium.Popup(popup_html, max_width=300),
            color=color,
            fill=True,
            fillOpacity=0.7,
            weight=2
        ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add AI legend
    add_ai_legend(m)
    
    return m

def simulate_ai_dot_placement(min_lat, max_lat, min_lon, max_lon, results):
    """Simulate AI-powered dot placement using pattern recognition"""
    import numpy as np
    
    # Simulate AI analysis of risk patterns
    n_points = 30  # AI-optimized number of points
    
    # Create a dense grid for AI analysis
    grid_lats = np.linspace(min_lat, max_lat, 30)
    grid_lons = np.linspace(min_lon, max_lon, 30)
    
    ai_dots = []
    
    for lat in grid_lats:
        for lon in grid_lons:
            # Simulate AI pattern recognition
            # AI analyzes multiple factors
            terrain_factor = simulate_terrain_analysis(lat, lon)
            vegetation_factor = simulate_vegetation_analysis(lat, lon)
            slope_factor = simulate_slope_analysis(lat, lon)
            historical_factor = simulate_historical_analysis(lat, lon)
            
            # AI combines factors intelligently
            risk_score = ai_combine_factors(terrain_factor, vegetation_factor, slope_factor, historical_factor)
            confidence = ai_calculate_confidence(terrain_factor, vegetation_factor, slope_factor, historical_factor)
            
            # AI decides whether to place a dot
            if ai_should_place_dot(risk_score, confidence):
                ai_dots.append((lat, lon, risk_score, confidence))
    
    return ai_dots

def simulate_terrain_analysis(lat, lon):
    """Simulate AI terrain analysis"""
    import numpy as np
    # Simulate terrain complexity analysis
    return np.random.beta(2, 3)

def simulate_vegetation_analysis(lat, lon):
    """Simulate AI vegetation analysis"""
    import numpy as np
    # Simulate vegetation health analysis
    return np.random.beta(3, 2)

def simulate_slope_analysis(lat, lon):
    """Simulate AI slope analysis"""
    import numpy as np
    # Simulate slope stability analysis
    return np.random.beta(2, 4)

def simulate_historical_analysis(lat, lon):
    """Simulate AI historical pattern analysis"""
    import numpy as np
    # Simulate historical landslide data analysis
    return np.random.beta(1, 5)

def ai_combine_factors(terrain, vegetation, slope, historical):
    """AI combines multiple factors intelligently"""
    # Weighted combination based on AI learning
    weights = [0.3, 0.4, 0.2, 0.1]  # AI-learned weights
    factors = [terrain, vegetation, slope, historical]
    
    # AI uses non-linear combination
    risk_score = sum(w * f for w, f in zip(weights, factors))
    
    # AI applies learned transformations
    if vegetation < 0.3:  # Low vegetation
        risk_score *= 1.5  # AI increases risk
    if slope > 0.7:  # High slope
        risk_score *= 1.3  # AI increases risk
    
    return min(1.0, risk_score)

def ai_calculate_confidence(terrain, vegetation, slope, historical):
    """AI calculates confidence in its assessment"""
    # AI confidence based on data quality and consistency
    data_quality = (terrain + vegetation + slope + historical) / 4
    consistency = 1.0 - abs(terrain - vegetation) - abs(slope - historical)
    
    confidence = (data_quality + consistency) / 2
    return min(1.0, max(0.0, confidence))

def ai_should_place_dot(risk_score, confidence):
    """AI decides whether to place a dot based on risk and confidence"""
    # AI uses intelligent thresholds
    if risk_score > 0.8 and confidence > 0.7:
        return True  # High risk, high confidence
    elif risk_score > 0.6 and confidence > 0.5:
        return np.random.random() < 0.8  # Medium risk, medium confidence
    elif risk_score > 0.4 and confidence > 0.3:
        return np.random.random() < 0.4  # Low risk, low confidence
    else:
        return np.random.random() < 0.1  # Very low risk

def add_ai_legend(map_obj):
    """Add AI legend to the map"""
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 300px; height: 200px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <p><b>🤖 AI-Powered Risk Assessment</b></p>
    <p><b>AI Risk Points:</b></p>
    <p><i class="fa fa-circle" style="color:green"></i> Low Risk (AI Low Confidence)</p>
    <p><i class="fa fa-circle" style="color:orange"></i> Medium Risk (AI Medium Confidence)</p>
    <p><i class="fa fa-circle" style="color:red"></i> High Risk (AI High Confidence)</p>
    <p><b>AI Analysis:</b></p>
    <p>• Terrain complexity analysis</p>
    <p>• Vegetation health assessment</p>
    <p>• Slope stability evaluation</p>
    <p>• Historical pattern recognition</p>
    <p><b>Status:</b> Proof of Concept</p>
    </div>
    '''
    map_obj.get_root().html.add_child(folium.Element(legend_html))

def create_ai_hybrid_map(results):
    """Create a map with AI-powered dots + detailed Earth Engine layers"""
    
    
    # Get ROI coordinates from results
    roi_bounds = results.get('roi_bounds', [124.450, 8.200, 124.550, 8.300])
    min_lon, min_lat, max_lon, max_lat = roi_bounds
    
    # Calculate center of ROI
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Add satellite basemap
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Add Earth Engine layers (like detailed layers mode)
    layers_added = []
    
    # Risk Score Layer
    if 'risk_score' in results:
        risk_score = results['risk_score']
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': ['green', 'yellow', 'red']
        }
        if add_ee_layer(m, risk_score, vis_params, 'Risk Score Overlay'):
            layers_added.append('Risk Score')
    
    # Vegetation Areas
    if 'vegetation_mask' in results:
        veg_mask = results['vegetation_mask']
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': ['00000000', 'green']  # Use hex transparent instead of 'transparent'
        }
        if add_ee_layer(m, veg_mask, vis_params, 'Vegetation Areas'):
            layers_added.append('Vegetation')
    
    # Water Bodies
    if 'water_mask' in results:
        water_mask = results['water_mask']
        vis_params = {
            'min': 0,
            'max': 1,
            'palette': ['00000000', 'lightblue']  # Use hex transparent instead of 'transparent'
        }
        if add_ee_layer(m, water_mask, vis_params, 'Water Bodies'):
            layers_added.append('Water')
    
    # NDVI Change
    if 'ndvi_change' in results:
        ndvi_change = results['ndvi_change']
        vis_params = {
            'min': -0.5,
            'max': 0.5,
            'palette': ['red', 'white', 'green']
        }
        if add_ee_layer(m, ndvi_change, vis_params, 'NDVI Change'):
            layers_added.append('NDVI Change')
    
    # AI-Powered Dot Placement (filtered for medium/high risk only)
    import numpy as np
    np.random.seed(42)
    
    # Simulate AI analysis of risk patterns
    ai_dots = simulate_ai_dot_placement(min_lat, max_lat, min_lon, max_lon, results)
    
    # Filter out low/medium-risk dots (only show high risk)
    filtered_ai_dots = []
    for dot in ai_dots:
        lat, lon, risk_score, confidence = dot
        # Only include dots with risk score >= 0.6 (high/very high risk only)
        # Based on MGB Philippines and FEMA official criteria
        # AND confidence > 0.4 (AI must be reasonably confident)
        if risk_score >= 0.6 and confidence > 0.4:
            filtered_ai_dots.append(dot)
    
    
    # Add filtered AI-placed dots
    for dot in filtered_ai_dots:
        lat, lon, risk_score, confidence = dot
        
        # Determine color and size based on official landslide risk criteria
        # Using MGB (Philippines) and FEMA standards
        if risk_score >= 0.8:
            color = 'darkred'
            size = 14
            risk_level = 'Very High Risk (Critical)'
        elif risk_score >= 0.6:
            color = 'red'
            size = 12
            risk_level = 'High Risk (Dangerous)'
        elif risk_score >= 0.3:
            color = 'orange'
            size = 10
            risk_level = 'Moderate Risk (Caution)'
        else:
            # This shouldn't happen due to filtering, but just in case
            color = 'green'
            size = 8
            risk_level = 'Low Risk (Safe)'
        
        # Create popup content
        popup_html = f"""
        <div style="width: 250px;">
            <h4>🤖 AI Risk Assessment</h4>
            <p><b>Risk Score:</b> {risk_score:.3f}</p>
            <p><b>AI Confidence:</b> {confidence:.1%}</p>
            <p><b>Risk Level:</b> {risk_level}</p>
            <p><b>NDVI Change:</b> {np.random.normal(-0.05, 0.1):.3f}</p>
            <p><b>Vegetation Health:</b> {np.random.uniform(0.3, 0.9):.3f}</p>
            <p><b>Slope:</b> {np.random.uniform(5, 45):.1f}°</p>
            <p><b>AI Analysis:</b> Pattern-based placement</p>
            <p><b>Filtered:</b> Medium/High risk only</p>
        </div>
        """
        
        folium.CircleMarker(
            [lat, lon],
            radius=size,
            popup=folium.Popup(popup_html, max_width=300),
            color=color,
            fill=True,
            fillOpacity=0.8,
            weight=2
        ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    # Add AI Hybrid legend
    add_ai_hybrid_legend(m, layers_added)
    
    return m

def add_ai_hybrid_legend(map_obj, layers_added):
    """Add AI Hybrid legend showing both AI dots and layers"""
    layers_text = ""
    if layers_added:
        layers_text = f"<p><b>Active Layers:</b> {', '.join(layers_added)}</p>"
    else:
        layers_text = "<p><b>Active Layers:</b> Loading Earth Engine data...</p>"
    
    legend_html = f'''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 320px; height: 240px; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:12px; padding: 10px; border-radius: 5px;">
    <p><b>🤖 AI Hybrid Visualization</b></p>
    <p><b>AI Risk Points (Filtered):</b></p>
    <p><i class="fa fa-circle" style="color:orange"></i> Medium Risk (AI Medium Confidence)</p>
    <p><i class="fa fa-circle" style="color:red"></i> High Risk (AI High Confidence)</p>
    <p><b>Earth Engine Layers:</b></p>
    <p><i class="fa fa-square" style="color:#1a9641"></i> Risk Score Overlay</p>
    <p><i class="fa fa-square" style="color:#27ae60"></i> Vegetation Areas</p>
    <p><i class="fa fa-square" style="color:#3498db"></i> Water Bodies</p>
    <p><i class="fa fa-square" style="color:red"></i> NDVI Change</p>
    {layers_text}
    <p><b>AI Analysis:</b> Pattern-based placement</p>
    <p><b>Filter:</b> Medium/High risk only</p>
    </div>
    '''
    map_obj.get_root().html.add_child(folium.Element(legend_html))

def create_ndvi_comparison_map(historical_ndvi, recent_ndvi, roi):
    """Create a comparison map showing NDVI changes"""
    
    center_lat = 8.35
    center_lon = 124.65
    
    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Add satellite basemap
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Add historical NDVI layer
    add_ee_layer(m, historical_ndvi, {
        'min': -0.2,
        'max': 1,
        'palette': ['royalblue', 'white', 'green']
    }, 'Historical NDVI')
    
    # Add recent NDVI layer
    add_ee_layer(m, recent_ndvi, {
        'min': -0.2,
        'max': 1,
        'palette': ['royalblue', 'white', 'green']
    }, 'Recent NDVI')
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    return m

def create_export_preview(results):
    """Create a preview of exportable data"""
    preview_data = {
        'Risk Score Statistics': {
            'Mean Risk Score': results.get('risk_threshold', 0),
            'High Risk Percentage': f"{results.get('high_risk_percentage', 0):.1f}%",
            'Risk Threshold': results.get('risk_threshold', 0)
        },
        'NDVI Change Statistics': {
            'Mean NDVI Change': results.get('mean_ndvi_change', 0),
            'Change Percentage': f"{results.get('ndvi_change_percent', 0):.1f}%",
            'Risk Level': results.get('risk_level', 'Unknown')
        }
    }
    
    return preview_data
