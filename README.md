# Homebox Analytics

A Streamlit-based analytics dashboard for Homebox.

## Configuration

The application is configured via environment variables. You can set these in a `.env` file in the root directory or pass them to the Docker container.

### Basic Configuration

| Variable | Description | Default |
| :--- | :--- | :--- |
| `HOMEBOX_URL` | The URL of your Homebox instance. | `https://homebox.example.com` |
| `HOMEBOX_TOKEN` | Your Homebox API token. | (Empty) |

### Advanced Configuration

| Variable | Description | Default |
| :--- | :--- | :--- |
| `STREAMLIT_SERVER_PORT` | The port the web server listens on. | `8501` |
| `APP_TITLE` | The title displayed in the application header. | `Homebox Business Tracker` |
| `PAGE_TITLE` | The title displayed in the browser tab. | `Homebox Analytics` |
| `CACHE_TTL` | Time-to-live for data caching in seconds. | (Infinite) |
| `AUTO_LOAD_DATA` | Automatically fetch data on startup if credentials are present (`true`/`false`). | `false` |

## Running with Docker

```bash
docker-compose up -d --build
```

## Running Locally

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2.  Run the app:
    ```bash
    streamlit run app.py
    ```

## Running with Portainer

To run this application in Portainer, you can use the following Stack configuration (docker-compose):

```yaml
version: '3'
services:
  homebox-analytics:
    image: ghcr.io/<your-github-username>/homebox-analytics:latest
    container_name: homebox-analytics
    ports:
      - "8501:8501"
    volumes:
      - homebox_data:/app/data
    environment:
      - HOMEBOX_URL=https://homebox.example.com
      - HOMEBOX_TOKEN=your_token_here
      - APP_TITLE=My Homebox Analytics
    restart: unless-stopped

volumes:
  homebox_data:
```
