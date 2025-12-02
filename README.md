# Homebox Analytics

A Streamlit-based analytics dashboard for Homebox.

## Workflow & Homebox Integration

This dashboard transforms Homebox into a powerful business inventory tracker for resellers. It relies on specific conventions in how you enter data in Homebox to calculate ROI, track sales velocity, and manage inventory.

### 1. Inventory Management
*   **Active Inventory**: Any item that is **not archived** and not in a special location (see below).
*   **Posted on Marketplace**: Check the **"Insured"** checkbox in Homebox. This dashboard uses the "Insured" flag to indicate an item is listed online.
*   **Stale Inventory**: Items held for more than **90 days** (based on `Purchase Date`) are automatically flagged in the "Stale Inventory" tab.

### 2. Recording Sales
To mark an item as sold and have it appear in the financial reports:
1.  Enter the **Sold Price**.
2.  Enter the **Sold Date**.
3.  **Archive** the item in Homebox.

### 3. Special Categories (Locations & Labels)
The analyzer looks for specific keywords in the **Location** or **Label** fields to categorize items:

| Keyword | Where to put it | Behavior |
| :--- | :--- | :--- |
| `Service`, `Labor`, `Other Income` | Label or Location | Treated as **Service Revenue** (100% profit, no COGS). |
| `Business Assets` | Location | Equipment kept for the business (e.g., shelving, camera). Deducted as expense, but separated from COGS. |
| `Loss` | Location | Items broken, lost, or given away. Tracked as "Losses". |

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
