package com.msemwafx.personal

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class Signal(
    val id: Int,
    val symbol: String,
    val direction: String,
    val status: String,
    val entry: String,
    val stop: String,
    val tp1: String,
    val generated: String
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MsemwaFxApp() }
    }
}

@Composable
fun MsemwaFxApp() {
    var apiUrl by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("Enter your private API URL and access token.") }
    var signals by remember { mutableStateOf(emptyList<Signal>()) }
    var loading by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    MaterialTheme {
        Scaffold(
            topBar = {
                TopAppBar(title = { Text("MsemwaFX") })
            }
        ) { padding ->
            Column(
                modifier = Modifier.fillMaxSize().padding(padding).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("PERSONAL INSTITUTIONAL TRADER", style = MaterialTheme.typography.labelLarge)
                OutlinedTextField(
                    value = apiUrl,
                    onValueChange = { apiUrl = it },
                    label = { Text("API base URL (https://...)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = token,
                    onValueChange = { token = it },
                    label = { Text("Private API token") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Button(
                    enabled = !loading && apiUrl.startsWith("https://") && token.isNotBlank(),
                    onClick = {
                        loading = true
                        message = "Connecting to MsemwaFX..."
                        scope.launch {
                            try {
                                signals = withContext(Dispatchers.IO) { fetchSignals(apiUrl.trimEnd('/'), token) }
                                message = "Connected • ${signals.size} signals loaded"
                            } catch (error: Exception) {
                                message = "Connection failed: ${error.message ?: "unknown error"}"
                            } finally {
                                loading = false
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (loading) "Connecting..." else "Connect / Refresh") }
                Text(message, style = MaterialTheme.typography.bodySmall)
                HorizontalDivider()
                Text("LATEST SIGNALS", style = MaterialTheme.typography.titleMedium)
                if (signals.isEmpty()) {
                    Text("No signals stored yet.")
                } else {
                    LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        items(signals) { signal ->
                            ElevatedCard(modifier = Modifier.fillMaxWidth()) {
                                Column(
                                    modifier = Modifier.padding(14.dp),
                                    verticalArrangement = Arrangement.spacedBy(4.dp)
                                ) {
                                    Text("${signal.symbol}  •  ${signal.direction}", style = MaterialTheme.typography.titleMedium)
                                    Text(signal.status, style = MaterialTheme.typography.labelLarge)
                                    Text("Entry: ${signal.entry}   SL: ${signal.stop}")
                                    Text("TP1: ${signal.tp1}")
                                    Text(signal.generated, style = MaterialTheme.typography.bodySmall)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun fetchSignals(baseUrl: String, token: String): List<Signal> {
    val connection = (URL("$baseUrl/api/v1/signals?limit=50").openConnection() as HttpURLConnection)
    try {
        connection.requestMethod = "GET"
        connection.connectTimeout = 12000
        connection.readTimeout = 12000
        connection.setRequestProperty("Authorization", "Bearer $token")
        val code = connection.responseCode
        val stream = if (code in 200..299) connection.inputStream else connection.errorStream
        val body = stream.bufferedReader().use { it.readText() }
        if (code !in 200..299) throw IllegalStateException("HTTP $code: $body")
        val array = JSONObject(body).getJSONArray("signals")
        return (0 until array.length()).map { index ->
            val row = array.getJSONObject(index)
            Signal(
                id = row.optInt("id"),
                symbol = row.optString("symbol"),
                direction = row.optString("direction"),
                status = row.optString("status"),
                entry = row.optString("entry", "—"),
                stop = row.optString("sl", "—"),
                tp1 = row.optString("tp1", "Not identified"),
                generated = row.optString("generated_at", "")
            )
        }
    } finally {
        connection.disconnect()
    }
}
