"""
Node monitoring and sensor simulation for GeoSafe Landslide Risk Mapper
Simulates real-world sensor deployment and monitoring capabilities
"""

import ee
import streamlit as st
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import json
from typing import Dict, List, Tuple, Optional
import folium
from folium import plugins

class SensorNode:
    """Simulates a deployed sensor node with multiple sensors"""
    
    def __init__(self, node_id: str, latitude: float, longitude: float, 
                 risk_level: str, deployment_date: datetime):
        self.node_id = node_id
        self.latitude = latitude
        self.longitude = longitude
        self.risk_level = risk_level
        self.deployment_date = deployment_date
        self.status = "active"
        self.battery_level = 100.0
        self.last_update = datetime.now()
        
        # Sensor readings history
        self.sensor_history = {
            'soil_moisture': [],
            'tilt_x': [],
            'tilt_y': [],
            'tilt_z': [],
            'vibration': [],
            'temperature': [],
            'humidity': [],
            'pressure': [],
            'timestamp': []
        }
    
    def generate_sensor_reading(self, base_risk_score: float = 0.5) -> Dict:
        """Generate realistic sensor readings based on risk level and environmental factors"""
        
        # Base values influenced by risk level
        risk_multiplier = 1.0 + (base_risk_score * 0.5)  # Higher risk = more extreme readings
        
        # Simulate environmental conditions
        current_time = datetime.now()
        hour = current_time.hour
        
        # Daily temperature cycle
        base_temp = 25 + 8 * np.sin(2 * np.pi * hour / 24)
        temperature = base_temp + random.gauss(0, 2) * risk_multiplier
        
        # Humidity inversely related to temperature
        humidity = max(30, min(95, 80 - (temperature - 20) * 2 + random.gauss(0, 5)))
        
        # Soil moisture based on risk and recent weather simulation
        soil_moisture = max(10, min(90, 50 + base_risk_score * 30 + random.gauss(0, 10)))
        
        # Tilt sensors - simulate ground movement
        tilt_x = random.gauss(0, 0.5) * risk_multiplier
        tilt_y = random.gauss(0, 0.5) * risk_multiplier
        tilt_z = random.gauss(0, 0.3) * risk_multiplier
        
        # Vibration - higher in high-risk areas
        vibration = max(0, random.gauss(0.1, 0.2) * risk_multiplier)
        
        # Atmospheric pressure
        pressure = 1013 + random.gauss(0, 10)
        
        reading = {
            'soil_moisture': round(soil_moisture, 2),
            'tilt_x': round(tilt_x, 3),
            'tilt_y': round(tilt_y, 3),
            'tilt_z': round(tilt_z, 3),
            'vibration': round(vibration, 4),
            'temperature': round(temperature, 1),
            'humidity': round(humidity, 1),
            'pressure': round(pressure, 1),
            'timestamp': current_time
        }
        
        # Store in history
        for key, value in reading.items():
            if key != 'timestamp':
                self.sensor_history[key].append(value)
        self.sensor_history['timestamp'].append(current_time)
        
        # Keep only last 100 readings
        for key in self.sensor_history:
            if len(self.sensor_history[key]) > 100:
                self.sensor_history[key] = self.sensor_history[key][-100:]
        
        # Update battery (simulate battery drain)
        self.battery_level = max(0, self.battery_level - random.uniform(0.1, 0.3))
        if self.battery_level <= 0:
            self.status = "low_battery"
        
        self.last_update = current_time
        return reading
    
    def get_status_summary(self) -> Dict:
        """Get current node status summary"""
        if not self.sensor_history['timestamp']:
            return {
                'status': self.status,
                'battery_level': self.battery_level,
                'last_update': self.last_update,
                'sensor_count': 0
            }
        
        latest_reading = self.generate_sensor_reading()
        
        return {
            'status': self.status,
            'battery_level': self.battery_level,
            'last_update': self.last_update,
            'sensor_count': len(self.sensor_history['timestamp']),
            'latest_reading': latest_reading
        }

class NodeDeploymentSystem:
    """Manages sensor node deployment and monitoring"""
    
    def __init__(self):
        self.nodes = {}
        self.deployment_history = []
    
    def suggest_node_placement(self, risk_results: Dict, max_nodes: int = 5) -> List[Dict]:
        """Suggest optimal node placement based on satellite analysis"""
        
        suggestions = []
        
        # Get risk hotspots
        if 'risk_hotspots' in risk_results:
            # Simulate hotspot detection and suggest placement
            roi_bounds = risk_results.get('roi_bounds', [124.60, 8.30, 124.70, 8.40])
            min_lon, min_lat, max_lon, max_lat = roi_bounds
            
            # Generate strategic placement points
            for i in range(max_nodes):
                # Place nodes in high-risk areas with some randomness
                lat = min_lat + (max_lat - min_lat) * (0.2 + 0.6 * random.random())
                lon = min_lon + (max_lon - min_lon) * (0.2 + 0.6 * random.random())
                
                # Determine risk level for this location
                risk_score = random.uniform(0.3, 0.9)  # Simulate risk score
                if risk_score > 0.7:
                    risk_level = "high"
                elif risk_score > 0.5:
                    risk_level = "medium"
                else:
                    risk_level = "low"
                
                suggestions.append({
                    'node_id': f"GEO-SAFE-{i+1:03d}",
                    'latitude': lat,
                    'longitude': lon,
                    'risk_level': risk_level,
                    'risk_score': risk_score,
                    'priority': "high" if risk_score > 0.7 else "medium",
                    'sensor_types': ['soil_moisture', 'tilt', 'vibration', 'environmental']
                })
        
        return suggestions
    
    def deploy_nodes(self, suggestions: List[Dict]) -> List[SensorNode]:
        """Deploy suggested nodes"""
        
        deployed_nodes = []
        
        for suggestion in suggestions:
            node = SensorNode(
                node_id=suggestion['node_id'],
                latitude=suggestion['latitude'],
                longitude=suggestion['longitude'],
                risk_level=suggestion['risk_level'],
                deployment_date=datetime.now()
            )
            
            self.nodes[node.node_id] = node
            deployed_nodes.append(node)
            
            # Record deployment
            self.deployment_history.append({
                'node_id': node.node_id,
                'location': (node.latitude, node.longitude),
                'deployment_date': node.deployment_date,
                'risk_level': node.risk_level
            })
        
        return deployed_nodes
    
    def get_all_node_status(self) -> Dict:
        """Get status of all deployed nodes"""
        status_summary = {}
        
        for node_id, node in self.nodes.items():
            status_summary[node_id] = node.get_status_summary()
        
        return status_summary
    
    def generate_alert(self, node_id: str, threshold_exceeded: str) -> Dict:
        """Generate alert for threshold exceeded"""
        return {
            'node_id': node_id,
            'alert_type': 'threshold_exceeded',
            'threshold': threshold_exceeded,
            'timestamp': datetime.now(),
            'severity': 'high' if threshold_exceeded in ['vibration', 'tilt'] else 'medium',
            'message': f"Node {node_id}: {threshold_exceeded} threshold exceeded"
        }

class DataFusionEngine:
    """Combines satellite data with ground sensor data for enhanced analysis"""
    
    def __init__(self):
        self.fusion_weights = {
            'satellite_risk': 0.6,
            'ground_sensors': 0.4
        }
    
    def fuse_data(self, satellite_risk: float, node_readings: Dict) -> Dict:
        """Fuse satellite risk data with ground sensor readings"""
        
        # Calculate ground-based risk indicators
        ground_risk_indicators = self._calculate_ground_risk(node_readings)
        
        # Weighted fusion
        fused_risk = (
            satellite_risk * self.fusion_weights['satellite_risk'] +
            ground_risk_indicators['composite_risk'] * self.fusion_weights['ground_sensors']
        )
        
        return {
            'fused_risk_score': fused_risk,
            'satellite_contribution': satellite_risk * self.fusion_weights['satellite_risk'],
            'ground_contribution': ground_risk_indicators['composite_risk'] * self.fusion_weights['ground_sensors'],
            'ground_indicators': ground_risk_indicators,
            'confidence_level': self._calculate_confidence(satellite_risk, ground_risk_indicators)
        }
    
    def _calculate_ground_risk(self, node_readings: Dict) -> Dict:
        """Calculate risk indicators from ground sensor data"""
        
        # Normalize sensor readings to risk scores (0-1)
        soil_moisture_risk = min(1.0, node_readings.get('soil_moisture', 50) / 80)
        tilt_risk = min(1.0, (abs(node_readings.get('tilt_x', 0)) + abs(node_readings.get('tilt_y', 0))) * 10)
        vibration_risk = min(1.0, node_readings.get('vibration', 0) * 20)
        
        # Composite ground risk
        composite_risk = (soil_moisture_risk * 0.4 + tilt_risk * 0.4 + vibration_risk * 0.2)
        
        return {
            'soil_moisture_risk': soil_moisture_risk,
            'tilt_risk': tilt_risk,
            'vibration_risk': vibration_risk,
            'composite_risk': composite_risk
        }
    
    def _calculate_confidence(self, satellite_risk: float, ground_indicators: Dict) -> float:
        """Calculate confidence level in fused assessment"""
        
        # Higher confidence when satellite and ground data agree
        risk_difference = abs(satellite_risk - ground_indicators['composite_risk'])
        confidence = max(0.5, 1.0 - risk_difference)
        
        return confidence

def create_node_monitoring_map(nodes: Dict, risk_results: Dict) -> folium.Map:
    """Create interactive map showing deployed nodes and risk areas"""
    
    # Get ROI bounds
    roi_bounds = risk_results.get('roi_bounds', [124.60, 8.30, 124.70, 8.40])
    min_lon, min_lat, max_lon, max_lat = roi_bounds
    
    # Calculate center
    center_lat = (min_lat + max_lat) / 2
    center_lon = (min_lon + max_lon) / 2
    
    # Create map
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
    
    # Add node markers
    for node_id, node in nodes.items():
        status = node.get_status_summary()
        latest_reading = status.get('latest_reading', {})
        
        # Determine marker color based on status
        if status['battery_level'] < 20:
            color = 'red'
        elif status['battery_level'] < 50:
            color = 'orange'
        else:
            color = 'green'
        
        # Create popup content
        popup_content = f"""
        <div style="width: 250px;">
            <h4>🌐 {node_id}</h4>
            <p><strong>Status:</strong> {status['status']}</p>
            <p><strong>Battery:</strong> {status['battery_level']:.1f}%</p>
            <p><strong>Risk Level:</strong> {node.risk_level}</p>
            <hr>
            <h5>📊 Latest Readings:</h5>
            <p><strong>Soil Moisture:</strong> {latest_reading.get('soil_moisture', 'N/A')}%</p>
            <p><strong>Temperature:</strong> {latest_reading.get('temperature', 'N/A')}°C</p>
            <p><strong>Humidity:</strong> {latest_reading.get('humidity', 'N/A')}%</p>
            <p><strong>Vibration:</strong> {latest_reading.get('vibration', 'N/A')}</p>
            <p><strong>Last Update:</strong> {status['last_update'].strftime('%Y-%m-%d %H:%M')}</p>
        </div>
        """
        
        # Add marker
        folium.Marker(
            location=[node.latitude, node.longitude],
            popup=folium.Popup(popup_content, max_width=300),
            tooltip=f"{node_id} - {node.risk_level.upper()} RISK",
            icon=folium.Icon(color=color, icon='wifi', prefix='fa')
        ).add_to(m)
    
    # Add layer control
    folium.LayerControl().add_to(m)
    
    return m

def simulate_node_data_generation(nodes: Dict, duration_hours: int = 24) -> Dict:
    """Simulate continuous data generation from nodes"""
    
    simulation_data = {}
    
    for node_id, node in nodes.items():
        # Generate readings for specified duration
        readings = []
        current_time = datetime.now()
        
        for hour in range(duration_hours):
            # Generate reading for this hour
            reading = node.generate_sensor_reading()
            reading['timestamp'] = current_time - timedelta(hours=duration_hours-hour)
            readings.append(reading)
        
        simulation_data[node_id] = readings
    
    return simulation_data
