# Deployment

One repository, two services.

## Render backend

Create a Blueprint from this repository using `render.yaml`, or create a Docker web service with:

- Dockerfile: `backend/Dockerfile`
- Build context: `backend`
- Health check: `/health`
- `ALLOWED_ORIGINS`: your Vercel frontend origin, for example `https://your-geosafe.vercel.app`

The Docker command runs one Uvicorn worker on Render’s `PORT`. Keep one instance because jobs are process-local. The bundled NOAH archive requires no Google or other credentials. Results use temporary storage and disappear on restarts or free-service sleep.

Check `https://your-api.onrender.com/health` before connecting the frontend.

## Vercel frontend

Import the same repository as a separate Vercel project:

- Root directory: `frontend`
- Framework: Vite
- Build command: `npm run build`
- Output directory: `dist`
- Environment variable: `VITE_API_URL=https://your-api.onrender.com`

Set the actual frontend origin in Render’s `ALLOWED_ORIGINS`, then redeploy both services after changing environment variables. Multiple allowed origins can be comma-separated. Do not add a path such as `/api` to `VITE_API_URL`.

The frontend variable is embedded at build time. A Vercel redeploy is needed to change it. Preview deployments need their own allowed origins if they should access the backend.

## Data dependencies

The backend reads public Earth Search metadata, public Sentinel-2 COGs, and public Copernicus DEM assets. No Google Earth Engine account is used. The map basemap comes from OpenFreeMap. Upstream services and internet access must be available.

For sustained use, size the Render instance based on measured memory and processing times. Free instances may cold-start and do not provide durable job state. This configuration prepares deployment; it does not provision services or claim that the app has already been deployed.
