# MsemwaFX personal service deployment

The production topology is one process running one scanner, one private read-only API, and one SQLite database.

## Railway setup

1. Create a Railway service from this repository and deploy the branch after review.
2. Ensure the service uses the repository's `railway.toml`.
3. Attach a persistent Railway Volume and mount it at `/data`. Without a persistent volume, SQLite data can be lost on redeploy/restart.
4. Set these variables in the Railway service:

- `DATABASE_PATH=/data/msemwafx.sqlite3`
- `API_ACCESS_TOKEN` = a long random secret (never commit it)
- `SCAN_INTERVAL_SECONDS=300`
- `TWELVEDATA_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_SCOUT_BOT_TOKEN` (if used)
- `TELEGRAM_CHAT_ID`
- `WA_PROVIDER`, `WA_PHONE`, `WA_APIKEY` (if WhatsApp delivery is enabled)

Railway supplies `PORT` automatically. The service exposes `/health` and the authenticated `/api/v1/signals` endpoint.

## Android app

Build the debug APK from the `android/` folder using Android Studio, or use the GitHub Actions workflow artifact. In the app, enter the deployed HTTPS service URL and the API access token.

The token is entered at runtime and is not committed in the repository. The current personal MVP does not persist the token on the device.

## Important deployment sequence

Do not disable the existing GitHub Actions production scanner until the Railway service is deployed, its persistent volume and secrets are configured, and its health endpoint responds successfully. After switching, leave only the Railway service running the production scanner. Do not manually run a second scanner at the same time.

The API is read-only; it cannot place broker orders. The Android app is a signal viewer, not an execution terminal.
