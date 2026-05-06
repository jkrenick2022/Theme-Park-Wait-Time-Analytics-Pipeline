import asyncio
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import os
import io
import boto3

# Helper function to convert timestamps into EST
def convert_to_eastern_time(timestamp_str):
    dt_utc = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
    dt_est = dt_utc.astimezone(ZoneInfo("America/New_York"))

    return dt_est.replace(tzinfo = None)

# Async function to get ride wait times for a given theme park
async def get_theme_park_data(client, base_url, property, theme_park, theme_park_id):
    # Format the endpoint with the theme park id
    formatted_url = base_url.format(id = theme_park_id)

    # Async function call
    response = (await client.get(formatted_url, timeout = 20.0)).json()

    # Create a object to store the data
    data = []

    # Loop over the request data
    for land in response.get("lands", []):
        land_id = land.get("id")
        land_name = land.get("name")

        for ride in land.get("rides", []):
            ride_id = ride.get("id")
            ride_name = ride.get("name")
            is_open = ride.get("is_open")
            wait_time = ride.get("wait_time") if is_open else None
            last_updated = convert_to_eastern_time(ride.get("last_updated"))

            # Append data to the list
            data.append(
                {
                    "property": property,
                    "theme_park": theme_park,
                    "land_id": land_id,
                    "land_name": land_name,
                    "ride_id": ride_id,
                    "ride_name": ride_name,
                    "is_open": is_open,
                    "wait_time": wait_time,
                    "last_updated": last_updated
                }
            )

    # Return the collected data
    return data

# Async function to get weather data based on latitude and longitude coordinates
async def get_current_weather(client, base_url, latitude, longitude):
    # Define query parameters
    params = {
        "latitude" : latitude,
        "longitude" : longitude,
        "current" : "precipitation,precipitation_probability,temperature_2m,apparent_temperature,relative_humidity_2m,visibility,wind_gusts_10m,wind_speed_10m,weather_code",
        "temperature_unit" : "fahrenheit",
        "wind_speed_unit" : "mph",
        "precipitation_unit" : "inch",
        "timezone" : "America/New_York"
    }

    # Call weather api
    response = await client.get(base_url, params = params, timeout = 20.0)

    # Make sure status is 200
    response.raise_for_status()

    # Return collected weather data
    return response.json()

# Async function to get weather data for a given theme park
async def get_park_weather(client, base_url, park_name):
    # Define coordinates map
    coords_map = {
        "Magic Kingdom" : (28.4177, -81.5812),
        "Epcot" : (28.3747, -81.5494),
        "Animal Kingdom" : (28.3590, -81.5900),
        "Hollywood Studios" : (28.3570, -81.5589),
        "Universal Studios" : (28.4726, -81.4695),
        "Islands of Adventure" : (28.4726, -81.4695),
        "Epic Universe" : (28.5154, -81.4638)
    }

    # Extract coordinates based on park
    latitude, longitude = coords_map[park_name]

    # Get park weather data
    response = await get_current_weather(client, base_url, latitude, longitude)

    # Extract the current weather data
    current = response.get("current", [])

    # Return park weather data
    return {
        "theme_park" : park_name,
        "weather_time_local" : datetime.fromisoformat(current.get("time")),
        "temperature_f": current.get("temperature_2m"),
        "apparent_temperature_f": current.get("apparent_temperature"),
        "humidity_pct": current.get("relative_humidity_2m"),
        "precip_in": current.get("precipitation"),
        "precip_prob_pct": current.get("precipitation_probability"),
        "visibility_m": current.get("visibility"),
        "wind_speed_mph": current.get("wind_speed_10m"),
        "wind_gusts_mph": current.get("wind_gusts_10m"),
        "weather_code": current.get("weather_code"),
    }

# Async function to combine all data together
async def collect_all_data(theme_park_base_url, weather_base_url):
    async with httpx.AsyncClient() as client:
        park_calls = [
            get_theme_park_data(client, theme_park_base_url, "Disney World", "Magic Kingdom", 6),
            get_theme_park_data(client, theme_park_base_url, "Disney World", "Epcot", 5),
            get_theme_park_data(client, theme_park_base_url, "Disney World", "Hollywood Studios", 7),
            get_theme_park_data(client, theme_park_base_url, "Disney World", "Animal Kingdom", 8),
            get_theme_park_data(client, theme_park_base_url, "Universal Studios Orlando", "Universal Studios", 65),
            get_theme_park_data(client, theme_park_base_url, "Universal Studios Orlando", "Islands of Adventure", 64),
            get_theme_park_data(client, theme_park_base_url, "Universal Studios Orlando", "Epic Universe", 334),
        ]

        weather_calls = [
            get_park_weather(client, weather_base_url, "Magic Kingdom"),
            get_park_weather(client, weather_base_url, "Epcot"),
            get_park_weather(client, weather_base_url, "Hollywood Studios"),
            get_park_weather(client, weather_base_url, "Animal Kingdom"),
            get_park_weather(client, weather_base_url, "Universal Studios"),
            get_park_weather(client, weather_base_url, "Islands of Adventure"),
            get_park_weather(client, weather_base_url, "Epic Universe"),
        ]

        park_data = await asyncio.gather(*park_calls)
        weather_data = await asyncio.gather(*weather_calls)

    all_rides = [row for park_list in park_data for row in park_list]

    df_parks = pd.DataFrame(all_rides)
    df_weather = pd.DataFrame(weather_data)
    df_final = df_parks.merge(df_weather, on="theme_park", how="left")
    df_final.insert(0, "collected_at", datetime.now(ZoneInfo("America/New_York")).replace(tzinfo=None))

    return df_final


# Function to get ENV variables
def get_env_variable(var_name):
    value = os.environ.get(var_name)
    if not value:
        raise ValueError(f"Missing environment variable: {var_name}")
    return value

# Function to upload the dataframe to AWS S3 as a Parquet file
def upload_to_s3(df, bucket_name):
    # Create a unique file name using the current timestamp
    current_time = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"raw-data/theme_park_data_{current_time}.parquet"

    # Initialize the S3 client
    s3_client = boto3.client('s3')

    # Convert pandas df to Parquet bytes in memory
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    # Upload to S3
    s3_client.upload_fileobj(buffer, bucket_name, filename)

    print(f"Success! Data uploaded to s3://{bucket_name}/{filename}")


# Main handler function called by AWS Lambda
def lambda_handler(event, context):
    # Fetch environment variables
    THEME_PARK_BASE_URL = get_env_variable("THEME_PARK_BASE_URL")
    WEATHER_BASE_URL = get_env_variable("WEATHER_BASE_URL")
    S3_BUCKET_NAME = get_env_variable("S3_BUCKET_NAME")

    print("Job Started...")

    try:
        df = asyncio.run(collect_all_data(THEME_PARK_BASE_URL, WEATHER_BASE_URL))
        upload_to_s3(df, S3_BUCKET_NAME)
        print("Job Finished!")
        return {"status": "success"}
    except Exception as e:
        print(f"Job Failed: {str(e)}")
        raise


# Local testing entry point
if __name__ == "__main__":
    lambda_handler(None, None)
