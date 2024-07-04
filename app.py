#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Apr 25 13:37:09 2024

@author: chrishornung
"""
import pandas as pd
from datetime import datetime, timedelta
import dash
from dash import dcc, html, Input, Output
import plotly.express as px

# Function to read data from Google Sheets or CSV URL
def read_data(url):
    if url.endswith('xlsx'):
        xls = pd.ExcelFile(url)
        data_dict = {}
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name, header=None)
            df.columns = ['DateandTime', 'ArrivedLeft', 'Address', 'Location']
            data_dict[sheet_name] = df
        return data_dict
    return None

# URLs of input files, separate them by commas
urls = [
    #SNGH/CHKD
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vRJLmScGNhDn3mbvK_p70EWYiT3GjBR-zu-Aj7CvtjlTXFlAWN-2moM9NnDauqx3HpoAVm9E3I14hTl/pub?output=xlsx"
]

# List to store dataframes
dfs = []

# Read data from each URL
for url in urls:
    data = read_data(url)
    if isinstance(data, dict):
        for df in data.values():
            dfs.append(df)
    elif isinstance(data, pd.DataFrame):
        dfs.append(data)

# Combine data from all URLs
combined_df = pd.concat(dfs, ignore_index=True)

# Keep only necessary columns
combined_df = combined_df[['DateandTime', 'ArrivedLeft', 'Address', 'Location']]

# Write combined dataframe to CSV
combined_df.to_csv('combined_data.csv', index=False)

# Read the CSV file
data = pd.read_csv("combined_data.csv")

# Convert 'DateandTime' column to datetime
data['DateandTime'] = pd.to_datetime(data['DateandTime'], format='%B %d, %Y at %I:%M%p')

# Sort the dataframe by 'DateandTime' and 'Location'
data = data.sort_values(by=['Location', 'DateandTime'])

# Remove duplicates from 'DateandTime' column
data.drop_duplicates(subset=['DateandTime'], keep='first', inplace=True)

# Calculate time elapsed in hours for each row
data['TimeElapsed'] = data.groupby('Location')['DateandTime'].diff().dt.total_seconds() / 3600

# Remove rows with NaN in 'TimeElapsed' column
data = data.dropna(subset=['TimeElapsed'])

# Remove rows where 'ArrivedLeft' is 'Arrived at location'
data = data[data['ArrivedLeft'] != 'Arrived at location']

# Save the output to a new CSV file
data.to_csv("combined_datawtimes.csv", index=False)

# Load the data
df = pd.read_csv("combined_datawtimes.csv")

# Convert DateandTime to datetime format
df['DateandTime'] = pd.to_datetime(df['DateandTime'])

# Get the min and max dates from the dataset
min_date = (df['DateandTime'].max() + timedelta(days=-30)).strftime('%Y-%m-%d')
max_date = (df['DateandTime'].max() + timedelta(days=1)).strftime('%Y-%m-%d')


# Initialize the Dash app
app = dash.Dash(__name__)

# Custom colors
colors = {
    'background': '#f9f9f9',
    'text': '#333333',
    'accent': '#007bff'
}

# Define the layout of the dashboard
app.layout = html.Div(style={'backgroundColor': colors['background'], 'fontFamily': 'Arial, sans-serif'}, children=[
    # Header
    html.H1(children='Duty Hours Dashboard', style={'textAlign': 'center', 'color': colors['accent'], 'marginTop': '40px'}),
    
    # Input boxes for start and end date
    html.Div([
        html.Label('Select Date Range', style={'color': colors['text'], 'marginRight': '10px'}),
        dcc.DatePickerRange(
            id='date-range-picker',
            start_date=min_date,
            end_date=max_date,
            display_format='YYYY-MM-DD',
            style={'marginRight': '20px'}
        ),
    ], style={'marginBottom': '30px', 'marginTop': '20px', 'textAlign': 'center'}),
    
    # Graph 1: Duty Hours per Specified Time Period
    html.Div([
        dcc.Graph(id='graph1', style={'height': '400px'}),
    ], style={'marginBottom': '40px', 'textAlign': 'center'}),
    
    # Graph 2: Duty Hours per Specified Time Period by Day
    html.Div([
        dcc.Graph(id='graph2', style={'height': '400px'}),
    ], style={'marginBottom': '40px', 'textAlign': 'center'}),

    # Graph 3: Duty Hours per Specified Time Period by Week
    html.Div([
        dcc.Graph(id='graph4', style={'height': '400px'}),
    ], style={'marginBottom': '40px', 'textAlign': 'center'}),
    
    # Graph 4: Duty Hours per Specified Time Period by Location
    html.Div([
        dcc.Graph(id='graph3', style={'height': '400px'}),
    ], style={'marginBottom': '40px', 'textAlign': 'center'}),
])

# Callback to update all graphs
@app.callback(
    [Output('graph1', 'figure'),
     Output('graph2', 'figure'),
     Output('graph3', 'figure'),
     Output('graph4', 'figure')],
    [Input('date-range-picker', 'start_date'),
     Input('date-range-picker', 'end_date')]
)
def update_graphs(start_date, end_date):
    # Filter data based on selected date range
    filtered_df = df[(df['DateandTime'] >= start_date) & (df['DateandTime'] <= end_date)]
    
    # Calculate total duty hours
    total_duty_hours = filtered_df['TimeElapsed'].sum()
    
    # Group by day and calculate total duty hours
    duty_hours_by_day = filtered_df.groupby(filtered_df['DateandTime'].dt.date)['TimeElapsed'].sum()
    
    # Group by location and calculate total duty hours
    duty_hours_by_location = filtered_df.groupby('Location')['TimeElapsed'].sum()
    
    # Group by week and calculate total duty hours
    duty_hours_by_week = filtered_df.groupby(filtered_df['DateandTime'].dt.strftime('%U'))['TimeElapsed'].sum()
    
    # Create bar chart for duty hours per specified time period
    fig1 = px.bar(x=['Total Duty Hours'], y=[total_duty_hours], text=[round(total_duty_hours)],
                 labels={'x': 'Date Range', 'y': 'Duty Hours'},
                 title='Duty Hours per Specified Time Period',
                 color_discrete_sequence=[colors['accent']])
    fig1.update_traces(texttemplate='%{text}', textposition='inside')  # Change text position to inside
    fig1.update_layout(plot_bgcolor=colors['background'], paper_bgcolor=colors['background'], font_color=colors['text'])
    
    # Create bar chart for duty hours per specified time period by day
    fig2 = px.bar(x=duty_hours_by_day.index, y=duty_hours_by_day.values, text=duty_hours_by_day.values.round(),
                 labels={'x': 'Day', 'y': 'Duty Hours'},
                 title='Duty Hours per Specified Time Period by Day',
                 color_discrete_sequence=[colors['accent']])
    fig2.update_traces(texttemplate='%{text}', textposition='inside')  # Change text position to inside
    fig2.update_layout(plot_bgcolor=colors['background'], paper_bgcolor=colors['background'], font_color=colors['text'])
    
    # Create bar chart for duty hours per specified time period by location
    fig3 = px.bar(x=duty_hours_by_location.index, y=duty_hours_by_location.values, text=duty_hours_by_location.values.round(),
                 labels={'x': 'Location', 'y': 'Duty Hours'},
                 title='Duty Hours per Specified Time Period by Location',
                 color_discrete_sequence=[colors['accent']])
    fig3.update_traces(texttemplate='%{text}', textposition='inside')  # Change text position to inside
    fig3.update_layout(plot_bgcolor=colors['background'], paper_bgcolor=colors['background'], font_color=colors['text'])
    
    # Create bar chart for duty hours per specified time period by week
    fig4 = px.bar(x=duty_hours_by_week.index, y=duty_hours_by_week.values, text=duty_hours_by_week.values.round(),
                 labels={'x': 'Week', 'y': 'Duty Hours'},
                 title='Duty Hours per Specified Time Period by Week',
                 color_discrete_sequence=[colors['accent']])
    fig4.update_traces(texttemplate='%{text}', textposition='inside')  # Change text position to inside
    fig4.update_layout(plot_bgcolor=colors['background'], paper_bgcolor=colors['background'], font_color=colors['text'])
    
    return fig1, fig2, fig3, fig4

# Run the app
# This is for Gunicorn compatibility
server = app.server
