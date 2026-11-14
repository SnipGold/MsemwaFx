# MsemwaFX Personal Android App

This is the personal-use Android client. It reads signals from the single cloud engine through the private MsemwaFX API; it does not run a second scanner.

## Build
Open the `android/` folder in Android Studio and build the `app` debug variant.

## Connect
Enter the deployed API base URL and the private API token. The token is requested at runtime and is not committed into the APK source.

The API must be deployed over HTTPS. Do not use a public unauthenticated endpoint.
